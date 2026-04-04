from core.interfaces import BaseParser


class ParserRegistry:
    """Strategy + Plugin pattern for parser selection.

    Parsers are evaluated in registration order; the first parser whose
    ``can_handle`` returns True is used.
    """

    def __init__(self) -> None:
        self._parsers: list[BaseParser] = []

    def register(self, parser: BaseParser) -> None:
        """Register a parser. First registered with can_handle() wins."""
        self._parsers.append(parser)

    def get_parser(self, file_type: str, content_hint: str = "") -> BaseParser:
        """Return first parser that can handle this file_type."""
        for parser in self._parsers:
            if parser.can_handle(file_type, content_hint):
                return parser
        raise ValueError(f"No parser registered for file_type={file_type!r}")
