from __future__ import annotations

from data_pipeline.validation import DataValidationError


def validate_delimited_shape(
    text: str,
    delimiter: str,
    *,
    max_columns: int,
    max_header_characters: int,
    max_cell_characters: int,
) -> None:
    """Bound logical CSV records before ``csv.reader`` materializes field lists."""

    if len(delimiter) != 1:
        raise ValueError("A delimited-text separator must be one character.")

    in_quotes = False
    field_characters = 0
    fields = 1
    logical_record = 0
    index = 0

    def check_field() -> None:
        limit = max_header_characters if logical_record == 0 else max_cell_characters
        if field_characters <= limit:
            return
        if logical_record == 0:
            raise DataValidationError(
                [
                    "The table header has a column name longer than "
                    f"{max_header_characters} characters."
                ]
            )
        raise DataValidationError(
            [
                f"Data row {logical_record} has a value longer than "
                f"{max_cell_characters:,} characters."
            ]
        )

    while index < len(text):
        character = text[index]
        if in_quotes:
            if character == '"':
                if index + 1 < len(text) and text[index + 1] == '"':
                    field_characters += 1
                    index += 2
                    check_field()
                    continue
                in_quotes = False
            else:
                field_characters += 1
                check_field()
            index += 1
            continue

        if character == '"' and field_characters == 0:
            in_quotes = True
        elif character == delimiter:
            check_field()
            fields += 1
            if fields > max_columns:
                raise DataValidationError(
                    [f"The table exceeds the {max_columns:,}-column limit."]
                )
            field_characters = 0
        elif character in "\r\n":
            check_field()
            logical_record += 1
            fields = 1
            field_characters = 0
            if character == "\r" and index + 1 < len(text) and text[index + 1] == "\n":
                index += 1
        else:
            field_characters += 1
            check_field()
        index += 1

    if in_quotes:
        raise ValueError("The delimited file contains an unterminated quoted field.")
    check_field()
