import os
import json
import base64
import gspread

GOOGLE_CREDENTIALS_BASE64_JSON = os.environ["GOOGLE_CREDENTIALS_JSON_BASE64"]

credentials_as_string = base64.b64decode(
    GOOGLE_CREDENTIALS_BASE64_JSON
).decode("utf-8")
credentials_as_dict = json.loads(credentials_as_string)
gc = gspread.service_account_from_dict(credentials_as_dict)
