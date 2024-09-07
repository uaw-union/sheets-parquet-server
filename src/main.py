from io import BytesIO
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
import pandas as pd
import polars as pl
from fastapi.middleware.cors import CORSMiddleware
import re
from .sheets import gc
from grist_api import GristDocAPI
import os
from cachetools import TTLCache
from cachetools.keys import hashkey

GRIST_SERVER_URL = os.environ["GRIST_SERVER_URL"]
GRIST_API_KEY = os.environ["GRIST_API_KEY"]

# FastAPI app setup
app = FastAPI()

# CORS middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_index_number_from_letter(letter: str) -> int:
    return ord(letter.lower()) - 96 - 1


def sanitize(name: str) -> str:
    """Sanitize the worksheet name for DBMS compatibility."""
    return re.sub(r"[^\w\s]", "", name).replace(" ", "_").lower()


# Define a cache with a maximum size of 100 items and a TTL of 15 seconds
cache = TTLCache(maxsize=100, ttl=15)


# Custom cache key function to handle multiple arguments
def custom_key(*args, **kwargs):
    return hashkey(*args, **kwargs)


async def get_worksheet_dataframe(
    sheet_id: str,
    worksheet_name: str,
    skip_rows: int = 0,
    header_row_index: int = 1,
    column_range: str = None,
) -> pl.DataFrame:
    cache_key = custom_key(
        sheet_id, worksheet_name, skip_rows, header_row_index
    )

    if cache_key in cache:
        return cache[cache_key]

    # Use direct fetch because fields needs to be restricted
    # to avoid internal error
    # Looks like: { sheets: [{ properties: { sheetId, title, sheetType } }]}

    metadata = gc.http_client.fetch_sheet_metadata(
        sheet_id, {"fields": "sheets.properties(sheetId,title)"}
    )

    # Attempt to reverse the sanitization to match the original worksheet name
    for sheet_dict in metadata["sheets"]:
        name = sheet_dict["properties"]["title"]

        sanitized_name = sanitize(name)
        if sanitized_name == worksheet_name:
            """
            I know this seems a bit weird, but going from:
            -> records -> pandas -> csv -> polars
            produces the best automatic type inference, and is
            the only situation I've found that will produce a
            boolean column from Google sheets TRUE or correctly parse
            int values
            """
            resp = gc.http_client.values_get(
                sheet_id,
                name,
            )
            all_values = resp["values"]

            skip_index = skip_rows + header_row_index
            data_values = all_values[skip_index:]
            header_row = all_values[header_row_index - 1]
            sanitized_header_row = [sanitize(h) for h in header_row]

            if column_range:
                start, end = column_range.split(":")
                # Get start and end index from letters
                start_index = get_index_number_from_letter(start)
                end_index = get_index_number_from_letter(end)

                def process_row_with_column_range(row):
                    result = row[start_index : end_index + 1] + [None] * (
                        len(sanitized_header_row)
                        - (end_index - start_index + 1)
                    )
                    return result

                data_values = [
                    process_row_with_column_range(row) for row in data_values
                ]
                sanitized_header_row = sanitized_header_row[
                    start_index : end_index + 1
                ]

            def process_row(row):
                result = row

                if len(row) == len(sanitized_header_row):
                    result = row

                if len(row) > len(sanitized_header_row):
                    result = row[: len(sanitized_header_row)]

                if len(row) < len(sanitized_header_row):
                    result = row + [None] * (
                        len(sanitized_header_row) - len(row)
                    )

                return result

            padded_data_values = [process_row(row) for row in data_values]

            # all_values = [row[header_row_index:] for row in all_values]
            pandas_df = pd.DataFrame(
                padded_data_values, columns=sanitized_header_row
            )
            csv_string = pandas_df.to_csv(index=False)
            csv_string_as_bytesio = BytesIO(csv_string.encode("utf-8"))
            polars_df = pl.read_csv(
                csv_string_as_bytesio, infer_schema_length=None
            )
            cache[cache_key] = polars_df
            return polars_df

    available_sanitized_names = [
        sanitize(sheet_dict["properties"]["title"])
        for sheet_dict in metadata["sheets"]
    ]

    raise HTTPException(
        status_code=404,
        detail="Worksheet not found. Available options: "
        + ", ".join(available_sanitized_names),
    )


@app.get("/google/{sheet_id}")
async def get_sheet_options(sheet_id: str):
    metadata = gc.http_client.fetch_sheet_metadata(
        sheet_id, {"fields": "sheets.properties(sheetId,title)"}
    )
    worksheet_names = [
        sanitize(sheet_dict["properties"]["title"])
        for sheet_dict in metadata["sheets"]
    ]
    return JSONResponse(content={"worksheets": worksheet_names})


@app.get("/google/{sheet_id}/{worksheet_key}.csv")
async def get_sheet_as_csv(
    sheet_id: str,
    worksheet_key: str,
    skip_rows: int = 0,
    header_row_index: int = 1,
    column_range: str = None,
):
    df = await get_worksheet_dataframe(
        sheet_id, worksheet_key, skip_rows, header_row_index, column_range
    )

    buffer = BytesIO()
    df.write_csv(buffer)

    return Response(content=buffer.getvalue(), media_type="text/csv")


@app.get("/google/{sheet_id}/{worksheet_key}.parquet")
async def get_sheet_as_parquet(
    sheet_id: str,
    worksheet_key: str,
    skip_rows: int = 0,
    header_row_index: int = 1,
    column_range: str = None,
):
    df = await get_worksheet_dataframe(
        sheet_id, worksheet_key, skip_rows, header_row_index, column_range
    )

    buffer = BytesIO()
    df.write_parquet(buffer)

    return Response(
        content=buffer.getvalue(), media_type="application/octet-stream"
    )


def transform_grist_records_to_pl_df(records, via_pandas=False):
    """
    2 transformations:
    - If the value is a list (not a tuple) and the first element is 'L', we want an
      array of all elements 1...end
    - If the value is a list and the first element is E, we want the result to be null
    """
    first_transformed_records = [
        {
            k: (
                v[1:]
                if isinstance(v, list) and len(v) > 0 and v[0] == "L"
                else v
            )
            for k, v in d.items()
        }
        for d in records
    ]
    second_transformed_records = [
        {
            k: (
                None
                if isinstance(v, list) and len(v) > 0 and v[0] == "E"
                else v
            )
            for k, v in d.items()
        }
        for d in first_transformed_records
    ]
    if via_pandas:
        as_pandas_df = pd.DataFrame(second_transformed_records)

        csv_string = as_pandas_df.to_csv(index=False)
        csv_string_as_bytesio = BytesIO(csv_string.encode("utf-8"))
        return pl.read_csv(csv_string_as_bytesio)
    else:
        return pl.DataFrame(second_transformed_records)


@app.get("/grist/{doc_id}/{table_id}.csv")
async def get_grist_doc(doc_id: str, table_id: str):
    doc = GristDocAPI(doc_id, api_key=GRIST_API_KEY, server=GRIST_SERVER_URL)
    records = doc.fetch_table(table_id)
    data_dicts = [record._asdict() for record in records]

    df = transform_grist_records_to_pl_df(data_dicts, via_pandas=True)
    buffer = BytesIO()
    df.write_csv(buffer)

    return Response(content=buffer.getvalue(), media_type="text/csv")


@app.get("/grist/{doc_id}/{table_id}.parquet")
async def get_grist_doc_parquet(doc_id: str, table_id: str):
    doc = GristDocAPI(doc_id, api_key=GRIST_API_KEY, server=GRIST_SERVER_URL)
    records = doc.fetch_table(table_id)
    data_dicts = [record._asdict() for record in records]

    df = transform_grist_records_to_pl_df(data_dicts, via_pandas=False)
    buffer = BytesIO()
    df.write_parquet(buffer)
    return Response(
        content=buffer.getvalue(), media_type="application/octet-stream"
    )
