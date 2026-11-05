"""Instance-local fix to the installed parser's string-parameter boundary.

The original parser exits string accumulation after its first text element;
a later literal <tool_call> then resets the call and silently truncates content.
Reuse its tokenizer, XML engine, type conversion and full-call extraction. Never
change the installed class, server tool parser, or structured streaming route.
"""

from vllm.tool_parsers.qwen3xml_tool_parser import (
    Qwen3XMLToolParser,
    StreamingXMLToolCallParser,
)


class StringBoundaryParser(StreamingXMLToolCallParser):
    def reset_streaming_state(self):
        super().reset_streaming_state()
        self.explicit_string_end = False
        self.invalid_string_boundary = False

    def string_parameter(self):
        return bool(self.current_param_name) and self._get_param_type(
            self.current_param_name
        ) in ["string", "str", "text", "varchar", "char", "enum"]

    def _preprocess_xml_chunk(self, chunk):
        if self.string_parameter():
            if chunk == "</parameter>":
                self.explicit_string_end = True
                self._pre_inside_parameter = False
                self._pre_param_buffer = ""
                self._pre_current_param_name = None
                return chunk
            return self._escape_xml_special_chars(chunk)
        return super()._preprocess_xml_chunk(chunk)

    def _end_element(self, name):
        if (
            name == "parameter" or name.startswith("parameter")
        ) and self.string_parameter():
            if not self.explicit_string_end:
                self.invalid_string_boundary = True
            self.explicit_string_end = False
        return super()._end_element(name)


def extract_complete_xml(tokenizer, text, request):
    parser = Qwen3XMLToolParser(tokenizer)
    parser.parser = StringBoundaryParser()
    result = parser.extract_tool_calls(text, request)
    if parser.parser.invalid_string_boundary:
        raise ValueError(
            "String parameter closed implicitly; refuse executable partial arguments"
        )
    return result
