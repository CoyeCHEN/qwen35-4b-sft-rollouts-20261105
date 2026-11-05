import ast
import json
import logging
from typing import Any, List, Optional

from sglang.srt.entrypoints.openai.protocol import Tool
from sglang.srt.function_call.base_format_detector import BaseFormatDetector
from sglang.srt.function_call.core_types import (
    StreamingParseResult,
    ToolCallItem,
    ToolCallParsingError,
    _GetInfoFunc,
)

logger = logging.getLogger(__name__)


class Qwen3CoderDetector(BaseFormatDetector):
    def __init__(self):
        super().__init__()

        # Sentinel tokens
        self.tool_call_start_token: str = "<tool_call>"
        self.tool_call_end_token: str = "</tool_call>"
        self.tool_call_prefix: str = "<function="
        self.function_end_token: str = "</function>"
        self.parameter_prefix: str = "<parameter="
        self.parameter_end_token: str = "</parameter>"

        # Streaming State
        # Base class already initializes _buffer, we just use it directly
        # No need to check with hasattr - we control the lifecycle through inheritance

        # Index pointing to the next character to be processed in buffer
        self.parsed_pos: int = 0
        # Parameter count inside the current tool being processed, used to determine whether to add comma
        self.current_tool_param_count: int = 0
        # Flag indicating whether current tool has already sent '{'
        self.json_started: bool = False

        # [FIX] New state flag: mark whether inside tool_call structure block
        self.is_inside_tool_call: bool = False

        # Initialize attributes that were missing in the original PR
        self.current_func_name: Optional[str] = None
        self.current_tool_param_names: set[str] = set()
        self._parameter_error: Optional[str] = None
        self._pending_error: Optional[ToolCallParsingError] = None

    def has_tool_call(self, text: str) -> bool:
        return self.tool_call_start_token in text

    def _get_arguments_config(
        self, func_name: str, tools: Optional[list[Tool]]
    ) -> dict:
        """Extract argument configuration for a function."""
        if tools is None:
            return {}
        for config in tools:
            try:
                config_type = config.type
                config_function = config.function
                config_function_name = config_function.name
            except AttributeError:
                continue

            if config_type == "function" and config_function_name == func_name:
                try:
                    params = config_function.parameters
                except AttributeError:
                    return {}

                if isinstance(params, dict) and "properties" in params:
                    return params["properties"]
                elif isinstance(params, dict):
                    return params
                else:
                    return {}
        logger.warning(f"Tool '{func_name}' is not defined in the tools list.")
        return {}

    def _convert_param_value(
        self, param_value: str, param_name: str, param_config: dict, func_name: str
    ) -> Any:
        """Convert parameter value based on its type in the schema."""
        # String values are opaque, including the literal text "null".
        field = param_config.get(param_name, {})
        if isinstance(field, dict) and field.get("type") == "string":
            return param_value
        if param_value.lower() == "null":
            return None

        if param_name not in param_config:
            if param_config != {}:
                logger.warning(
                    f"Parsed parameter '{param_name}' is not defined in the tool "
                    f"parameters for tool '{func_name}', directly returning the string value."
                )
            return param_value

        if (
            isinstance(param_config[param_name], dict)
            and "type" in param_config[param_name]
        ):
            param_type = str(param_config[param_name]["type"]).strip().lower()
        else:
            param_type = "string"
        if param_type in ["string", "str", "text", "varchar", "char", "enum"]:
            return param_value
        elif (
            param_type.startswith("int")
            or param_type.startswith("uint")
            or param_type.startswith("long")
            or param_type.startswith("short")
            or param_type.startswith("unsigned")
        ):
            try:
                param_value = int(param_value)
            except Exception:
                logger.warning(
                    f"Parsed value '{param_value}' of parameter '{param_name}' is not an integer in tool "
                    f"'{func_name}', degenerating to string."
                )
            return param_value
        elif param_type.startswith("num") or param_type.startswith("float"):
            try:
                maybe_convert = (
                    False if "." in param_value or "e" in param_value.lower() else True
                )
                param_value: float = float(param_value)
                if maybe_convert and param_value.is_integer():
                    param_value = int(param_value)
            except Exception:
                logger.warning(
                    f"Parsed value '{param_value}' of parameter '{param_name}' is not a float in tool "
                    f"'{func_name}', degenerating to string."
                )
            return param_value
        elif param_type in ["boolean", "bool", "binary"]:
            param_value = param_value.lower()
            if param_value not in ["true", "false"]:
                logger.warning(
                    f"Parsed value '{param_value}' of parameter '{param_name}' is not a boolean (`true` of `false`) in tool '{func_name}', degenerating to false."
                )
            return param_value == "true"
        else:
            if (
                param_type in ["object", "array", "arr"]
                or param_type.startswith("dict")
                or param_type.startswith("list")
            ):
                try:
                    param_value = json.loads(param_value)
                    return param_value
                except Exception:
                    logger.warning(
                        f"Parsed value '{param_value}' of parameter '{param_name}' cannot be parsed with json.loads in tool "
                        f"'{func_name}', will try other methods to parse it."
                    )
            try:
                param_value = ast.literal_eval(param_value)  # safer
            except Exception:
                logger.warning(
                    f"Parsed value '{param_value}' of parameter '{param_name}' cannot be converted via Python `ast.literal_eval()` in tool '{func_name}', degenerating to string."
                )
            return param_value

    def _parameter_end(self, value: str, name: str, config: dict) -> Optional[int]:
        """Find the explicit closing tag without interpreting JSON string contents."""
        field = config.get(name, {})
        kind = field.get("type") if isinstance(field, dict) else None
        if kind not in ("array", "object"):
            end = value.find(self.parameter_end_token)
            return end if end >= 0 else None

        stripped = value.lstrip()
        leading = len(value) - len(stripped)
        try:
            parsed, end = json.JSONDecoder().raw_decode(stripped)
        except json.JSONDecodeError as error:
            # A chunk can end anywhere inside a valid JSON value. Only the
            # explicit generation-finish event can reject an unfinished value.
            self._parameter_error = f"Invalid or incomplete JSON for {name!r}: {error.msg}"
            return None
        self._parameter_error = None
        expected = list if kind == "array" else dict
        if not isinstance(parsed, expected):
            raise ToolCallParsingError(f"Expected a JSON {kind} for parameter {name!r}")
        tail = stripped[end:]
        closing = tail.lstrip()
        if not closing or (len(closing) < len(self.parameter_end_token) and self.parameter_end_token.startswith(closing)):
            return None
        if not closing.startswith(self.parameter_end_token):
            raise ToolCallParsingError(f"Expected </parameter> after JSON parameter {name!r}")
        self._parameter_error = None
        return leading + end + len(tail) - len(closing)

    def finish_stream(self) -> StreamingParseResult:
        """Finish without inventing fields, delimiters, or a partial tool action."""
        if self._pending_error is not None:
            raise self._pending_error
        if self.is_inside_tool_call or self.current_func_name is not None:
            raise ToolCallParsingError(self._parameter_error or "Incomplete qwen3_coder tool call")
        remaining = self._buffer[self.parsed_pos :]
        self._buffer = ""
        self.parsed_pos = 0
        return StreamingParseResult(normal_text=remaining)

    def detect_and_parse(self, text: str, tools: List[Tool]) -> StreamingParseResult:
        """Use the same typed parameter boundaries as the streaming path."""
        detector = type(self)()
        result = detector.parse_streaming_increment(text, tools)
        final = detector.finish_stream()
        merged = {}
        for delta in result.calls:
            call = merged.setdefault(
                delta.tool_index, {"name": None, "parameters": ""}
            )
            if delta.name:
                call["name"] = delta.name
            call["parameters"] += delta.parameters or ""
        calls = [
            ToolCallItem(tool_index=index, name=call["name"], parameters=call["parameters"])
            for index, call in merged.items()
        ]
        return StreamingParseResult(
            normal_text=result.normal_text + final.normal_text, calls=calls
        )

    def parse_streaming_increment(
        self, new_text: str, tools: List[Tool]
    ) -> StreamingParseResult:
        """Defer rejection until the actual generation-finish event."""
        if self._pending_error is not None:
            return StreamingParseResult()
        try:
            return self._parse_streaming_increment(new_text, tools)
        except ToolCallParsingError as error:
            self._pending_error = error
            return StreamingParseResult()

    def _parse_streaming_increment(
        self, new_text: str, tools: List[Tool]
    ) -> StreamingParseResult:
        self._buffer += new_text

        # Guard against empty buffer
        if not self._buffer:
            return StreamingParseResult()

        calls = []
        normal_text_chunks = []

        while True:
            # Working text slice
            current_slice = self._buffer[self.parsed_pos :]

            # Optimization: If almost empty, wait for more
            if not current_slice:
                break

            # -------------------------------------------------------
            # 1. Priority detection: check if it's the start of Tool Call
            # -------------------------------------------------------
            if current_slice.startswith(self.tool_call_start_token):
                if self.is_inside_tool_call:
                    raise ToolCallParsingError("Nested tool_call block")
                self.parsed_pos += len(self.tool_call_start_token)
                self.is_inside_tool_call = True
                continue

            # -------------------------------------------------------
            # 2. Function Name: <function=name>
            # -------------------------------------------------------
            if self.is_inside_tool_call and current_slice.startswith(
                self.tool_call_prefix
            ):
                end_angle = current_slice.find(">")
                if end_angle != -1:
                    func_name = current_slice[len(self.tool_call_prefix) : end_angle]
                    if not func_name or self.current_func_name is not None:
                        raise ToolCallParsingError("Missing or nested function header")

                    self.current_tool_id += 1
                    self.current_tool_name_sent = True
                    self.current_tool_param_count = 0
                    self.current_tool_param_names = set()
                    self._parameter_error = None
                    self.json_started = False
                    self.current_func_name = func_name

                    calls.append(
                        ToolCallItem(
                            tool_index=self.current_tool_id,
                            name=func_name,
                            parameters="",
                        )
                    )

                    self.parsed_pos += end_angle + 1
                    continue
                else:
                    # Incomplete tag
                    break

            # -------------------------------------------------------
            # 3. Parameter: <parameter=name>value...
            # -------------------------------------------------------
            if self.is_inside_tool_call and current_slice.startswith(
                self.parameter_prefix
            ):
                if self.current_func_name is None:
                    raise ToolCallParsingError("Tool parameter encountered without a function header")
                name_end = current_slice.find(">")
                if name_end != -1:
                    value_start_idx = name_end + 1
                    rest_of_slice = current_slice[value_start_idx:]

                    param_name = current_slice[len(self.parameter_prefix) : name_end]
                    if param_name in self.current_tool_param_names:
                        raise ToolCallParsingError(f"Duplicate parameter {param_name!r}")
                    param_config = self._get_arguments_config(self.current_func_name, tools)
                    end_pos = self._parameter_end(rest_of_slice, param_name, param_config)
                    if end_pos is not None:
                        end_token_len = len(self.parameter_end_token)
                        raw_value = rest_of_slice[:end_pos]

                        # Cleanup value
                        if raw_value.startswith("\n"):
                            raw_value = raw_value[1:]
                        if raw_value.endswith("\n"):
                            raw_value = raw_value[:-1]

                        # JSON Construction
                        if not self.json_started:
                            calls.append(
                                ToolCallItem(
                                    tool_index=self.current_tool_id, parameters="{"
                                )
                            )
                            self.json_started = True

                        param_config = self._get_arguments_config(
                            self.current_func_name, tools
                        )
                        converted_val = self._convert_param_value(
                            raw_value, param_name, param_config, self.current_func_name
                        )

                        # Construct JSON fragment: "key": value
                        # Note: We must be careful with json.dumps to ensure valid JSON streaming
                        json_key_val = f"{json.dumps(param_name)}: {json.dumps(converted_val, ensure_ascii=False)}"

                        if self.current_tool_param_count > 0:
                            fragment = f", {json_key_val}"
                        else:
                            fragment = json_key_val

                        calls.append(
                            ToolCallItem(
                                tool_index=self.current_tool_id, parameters=fragment
                            )
                        )
                        self.current_tool_param_count += 1
                        self.current_tool_param_names.add(param_name)

                        # Advance cursor
                        total_len = (name_end + 1) + end_pos + end_token_len
                        self.parsed_pos += total_len
                        continue

                # Incomplete parameter tag or value
                break

            # -------------------------------------------------------
            # 4. Function End: </function>
            # -------------------------------------------------------
            if self.is_inside_tool_call and current_slice.startswith(
                self.function_end_token
            ):
                if self.current_func_name is None:
                    raise ToolCallParsingError("Function end encountered without a function header")
                if not self.json_started:
                    calls.append(
                        ToolCallItem(tool_index=self.current_tool_id, parameters="{")
                    )
                    self.json_started = True

                calls.append(
                    ToolCallItem(tool_index=self.current_tool_id, parameters="}")
                )
                self.parsed_pos += len(self.function_end_token)
                self.current_func_name = None
                continue

            # -------------------------------------------------------
            # 5. Tool Call End: </tool_call>
            # -------------------------------------------------------
            if self.is_inside_tool_call and current_slice.startswith(
                self.tool_call_end_token
            ):
                if self.current_func_name is not None:
                    raise ToolCallParsingError("Tool call ended before its function was closed")
                self.parsed_pos += len(self.tool_call_end_token)
                self.is_inside_tool_call = False  # [FIX] Exit tool call region
                continue

            # -------------------------------------------------------
            # 6. Handling content / whitespace / normal text
            # -------------------------------------------------------
            # If current position is not the start of a tag (i.e., doesn't start with <), it might be plain text,
            # or a newline between two tags.
            # But we need to be careful not to output truncated tags like "<fun" as text.

            next_open_angle = current_slice.find("<")

            if next_open_angle == -1:
                # This entire segment is plain text
                if not self.is_inside_tool_call:
                    normal_text_chunks.append(current_slice)
                elif current_slice.strip():
                    raise ToolCallParsingError("Unexpected text outside a parameter in tool call")
                self.parsed_pos += len(current_slice)
                continue

            elif next_open_angle == 0:
                # Looks like a Tag, but doesn't match any known Tag above

                possible_tags = (
                    [self.tool_call_start_token]
                    if not self.is_inside_tool_call
                    else [
                        self.tool_call_start_token,
                        self.tool_call_end_token,
                        self.tool_call_prefix,
                        self.function_end_token,
                        self.parameter_prefix,
                        self.parameter_end_token,
                    ]
                )

                is_potential_tag = False
                for tag in possible_tags:
                    if tag.startswith(current_slice):
                        is_potential_tag = True
                        break

                if is_potential_tag:
                    break  # Wait for more
                else:
                    # Just a plain '<' symbol
                    if not self.is_inside_tool_call:
                        normal_text_chunks.append("<")
                    else:
                        raise ToolCallParsingError("Unexpected tag outside a parameter in tool call")
                    self.parsed_pos += 1
                    continue

            else:
                # '<' is in the middle
                text_segment = current_slice[:next_open_angle]
                if not self.is_inside_tool_call:
                    normal_text_chunks.append(text_segment)
                elif text_segment.strip():
                    raise ToolCallParsingError("Unexpected text outside a parameter in tool call")
                self.parsed_pos += next_open_angle
                continue

        # Memory Cleanup: Slice the buffer
        # Keep unparsed part, discard parsed part
        if self.parsed_pos > 0:
            self._buffer = self._buffer[self.parsed_pos :]
            self.parsed_pos = 0

        normal_text = "".join(normal_text_chunks) if normal_text_chunks else ""
        return StreamingParseResult(calls=calls, normal_text=normal_text)

    def supports_structural_tag(self) -> bool:
        return False

    def structure_info(self) -> _GetInfoFunc:
        raise NotImplementedError
