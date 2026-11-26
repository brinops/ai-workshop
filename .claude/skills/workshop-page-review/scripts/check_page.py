"""Verify the workshop page with the Python standard library."""

from html.parser import HTMLParser
from pathlib import Path


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = set()
        self.ids = set()
        self.anchors = []
        self.has_stylesheet = False
        self.has_script = False

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.has_stylesheet |= attrs.get("href") == "styles.css"
        if tag == "a" and (attrs.get("href") or "").startswith("#"):
            self.anchors.append(attrs["href"][1:])
        self.has_script |= tag == "script" or any(name.startswith("on") for name in attrs)


def main():
    page_dir = Path("demo/static-page")
    page = Page()
    page.feed((page_dir / "index.html").read_text(encoding="utf-8"))
    page.close()
    checks = (
        ({"html", "title", "main", "h1"} <= page.tags, "Provide html, title, main and h1 elements."),
        (page.has_stylesheet, "Link the local styles.css file."),
        (bool((page_dir / "styles.css").read_text(encoding="utf-8").strip()), "Provide a stylesheet."),
        (bool(page.anchors) and all(anchor in page.ids for anchor in page.anchors),
         "Link the primary action to a section on the page."),
        (not page.has_script, "Keep the page free of JavaScript."),
    )
    errors = [message for passed, message in checks if not passed]
    if errors:
        raise SystemExit("\n".join(errors))
    print("Static page checks passed.")


if __name__ == "__main__":
    main()
