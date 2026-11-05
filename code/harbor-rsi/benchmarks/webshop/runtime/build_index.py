import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PRODUCT_FILE = BASE_DIR / "data" / "items_shuffle_1000.json"


def normalized_products(products):
    seen = set()
    result = []
    for product in products:
        asin = product["asin"]
        if asin == "nan" or len(asin) > 10 or asin in seen:
            continue
        seen.add(asin)

        normalized = dict(product)
        normalized["Title"] = product["name"]
        normalized["Description"] = product["full_description"]
        small_description = product["small_description"]
        normalized["BulletPoints"] = (
            small_description
            if isinstance(small_description, list)
            else [small_description]
        )

        options = {}
        customization_options = product["customization_options"]
        if customization_options:
            for option_name, option_contents in customization_options.items():
                if option_contents is None:
                    continue
                option_values = []
                for option_content in option_contents:
                    option_values.append(
                        option_content["value"].strip().replace("/", " | ").lower()
                    )
                options[option_name.lower()] = option_values
        normalized["options"] = options

        result.append(normalized)
    return result


def product_document(product):
    options = product.get("options", {})
    option_texts = []
    for option_name, option_contents in options.items():
        option_contents_text = ", ".join(option_contents)
        option_texts.append(f"{option_name}: {option_contents_text}")
    option_text = ", and ".join(option_texts)

    return {
        "id": product["asin"],
        "contents": " ".join(
            [
                product["Title"],
                product["Description"],
                product["BulletPoints"][0],
                option_text,
            ]
        ).lower(),
        "product": product,
    }


def write_documents(path, products):
    path.mkdir(parents=True, exist_ok=True)
    with (path / "documents.jsonl").open("w", encoding="utf-8") as handle:
        for product in products:
            handle.write(json.dumps(product_document(product)) + "\n")


def main():
    with PRODUCT_FILE.open(encoding="utf-8") as handle:
        products = normalized_products(json.load(handle))

    write_documents(BASE_DIR / "search_engine" / "resources_100", products[:100])
    write_documents(BASE_DIR / "search_engine" / "resources_1k", products[:1000])
    write_documents(BASE_DIR / "search_engine" / "resources", products)
    write_documents(BASE_DIR / "search_engine" / "resources_100k", products[:100000])


if __name__ == "__main__":
    main()
