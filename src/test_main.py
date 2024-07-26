import pytest
from httpx import AsyncClient
from .main import app
from unittest.mock import patch, Mock


# Mock Google Sheets
worksheet_mock = Mock()
worksheet_mock.title = "Worksheet1"
worksheet_mock.get_all_records.return_value = [
    {"Name": "John Doe", "Age": 30},
    {"Name": "Jane Doe", "Age": 25},
]

spreadsheet_mock = Mock()
spreadsheet_mock.worksheets.return_value = [worksheet_mock]
spreadsheet_mock.worksheet.return_value = worksheet_mock


@pytest.mark.asyncio
@patch("src.sheets.gc.open_by_key", return_value=spreadsheet_mock)
async def test_get_sheet_options(mock_open_by_key):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/test_sheet_id_1")
        print("Response")
        print(response.json())
        assert response.status_code == 200
        assert response.json() == {"worksheets": ["Worksheet1"]}


@pytest.mark.asyncio
@patch("src.sheets.gc.open_by_key", return_value=spreadsheet_mock)
async def test_get_sheet_as_csv(mock_open_by_key):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/test_sheet_id_1/worksheet1.csv")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
    # Add more assertions for the CSV content


@pytest.mark.asyncio
@patch("src.sheets.gc.open_by_key", return_value=spreadsheet_mock)
async def test_get_sheet_as_parquet(mock_open_by_key):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/test_sheet_id_1/worksheet1.parquet")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/octet-stream"
