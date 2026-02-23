from typing import Dict, Optional

import requests


NOTION_BASE_URL = "https://api.notion.com/v1"
REQUIRED_PROPERTIES = [
    "Set ID",
    "Persona",
    "Market",
    "Funnel Stage",
    "Ad Label",
    "Language",
    "Headline",
    "Primary Text",
    "CTA",
    "Video ID",
    "Video URL",
    "Reused?",
    "Status",
]

OPTIONAL_PROPERTIES = ["Tag", "Iteration", "Notes"]

DEFAULT_PROPERTY_TYPES = {
    "Set ID": "title",
    "Persona": "rich_text",
    "Market": "rich_text",
    "Funnel Stage": "select",
    "Ad Label": "rich_text",
    "Language": "select",
    "Headline": "rich_text",
    "Primary Text": "rich_text",
    "CTA": "rich_text",
    "Video ID": "rich_text",
    "Video URL": "url",
    "Reused?": "checkbox",
    "Status": "status",
}


def check_required_properties(property_types: Dict[str, str]) -> Dict[str, str]:
    return {name: property_types.get(name, "") for name in REQUIRED_PROPERTIES}


class NotionClient:
    def __init__(self, api_key: str, database_id: str, data_source_id: Optional[str], notion_version: str):
        self.api_key = api_key
        self.database_id = database_id
        self.data_source_id = data_source_id
        self.notion_version = notion_version
        self._property_types = None

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": self.notion_version,
            "Content-Type": "application/json",
        }

    def get_property_types(self) -> Dict[str, str]:
        if self._property_types is not None:
            return self._property_types

        response = requests.get(
            f"{NOTION_BASE_URL}/databases/{self.database_id}",
            headers=self._headers(),
            timeout=20,
        )
        if response.status_code >= 300:
            raise RuntimeError("Failed to retrieve database schema.")

        data = response.json()
        properties = data.get("properties", {})
        self._property_types = {name: spec.get("type") for name, spec in properties.items()}
        return self._property_types

    def create_page(self, properties: Dict) -> Dict:
        parent = {"type": "database_id", "database_id": self.database_id}
        if self.data_source_id:
            parent = {"type": "data_source_id", "data_source_id": self.data_source_id}

        response = requests.post(
            f"{NOTION_BASE_URL}/pages",
            headers=self._headers(),
            json={"parent": parent, "properties": properties},
            timeout=20,
        )
        if response.status_code >= 300:
            raise RuntimeError(f"Failed to create Notion page ({response.status_code}): {response.text}")
        return response.json()

    def update_page(self, page_id: str, properties: Dict) -> Dict:
        response = requests.patch(
            f"{NOTION_BASE_URL}/pages/{page_id}",
            headers=self._headers(),
            json={"properties": properties},
            timeout=20,
        )
        if response.status_code >= 300:
            raise RuntimeError(f"Failed to update Notion page ({response.status_code}): {response.text}")
        return response.json()

    def query_database(self, filter_obj: Optional[Dict] = None, sorts: Optional[list] = None) -> list:
        body: Dict = {}
        if filter_obj:
            body["filter"] = filter_obj
        if sorts:
            body["sorts"] = sorts
        response = requests.post(
            f"{NOTION_BASE_URL}/databases/{self.database_id}/query",
            headers=self._headers(),
            json=body,
            timeout=20,
        )
        if response.status_code >= 300:
            raise RuntimeError(f"Database query failed ({response.status_code}): {response.text}")
        return response.json().get("results", [])


def _text_value(value: str) -> Dict:
    return {"type": "text", "text": {"content": value}}


def _build_property(value, prop_type: str) -> Optional[Dict]:
    if value is None:
        return None
    if prop_type == "title":
        return {"title": [_text_value(str(value))]}
    if prop_type == "rich_text":
        return {"rich_text": [_text_value(str(value))]}
    if prop_type == "select":
        return {"select": {"name": str(value)}}
    if prop_type == "multi_select":
        return {"multi_select": [{"name": str(value)}]}
    if prop_type == "status":
        return {"status": {"name": str(value)}}
    if prop_type == "checkbox":
        return {"checkbox": bool(value)}
    if prop_type == "url":
        return {"url": str(value)} if value else None
    return {"rich_text": [_text_value(str(value))]}


def build_notion_properties(
    creative: Dict,
    inputs: Dict,
    set_id: str,
    video_url: Optional[str],
    status: str,
    property_types: Optional[Dict[str, str]],
    tag: str = "Draft",
    iteration: int = 1,
) -> Dict:
    property_types = property_types or DEFAULT_PROPERTY_TYPES

    values = {
        "Set ID": set_id,
        "Persona": inputs.get("persona"),
        "Market": inputs.get("market"),
        "Funnel Stage": creative.get("funnel_stage"),
        "Ad Label": creative.get("ad_label"),
        "Language": creative.get("language"),
        "Headline": creative.get("headline"),
        "Primary Text": creative.get("primary_text"),
        "CTA": creative.get("cta"),
        "Video ID": creative.get("video_id"),
        "Video URL": video_url,
        "Reused?": creative.get("reused"),
        "Status": status,
    }

    properties: Dict[str, Dict] = {}
    missing = []
    for name in REQUIRED_PROPERTIES:
        prop_type = property_types.get(name)
        if not prop_type:
            missing.append(name)
            continue
        built = _build_property(values.get(name), prop_type)
        if built is not None:
            properties[name] = built

    if missing:
        raise RuntimeError(f"Notion database is missing required properties: {', '.join(missing)}")

    # Optional properties: Tag, Iteration, Notes
    if "Tag" in property_types:
        built = _build_property(tag, property_types["Tag"])
        if built is not None:
            properties["Tag"] = built
    if "Iteration" in property_types:
        properties["Iteration"] = {"number": iteration}

    return properties


def build_update_properties(
    video_url: Optional[str],
    status: str,
    property_types: Optional[Dict[str, str]],
) -> Dict:
    property_types = property_types or DEFAULT_PROPERTY_TYPES
    update_values = {
        "Video URL": video_url,
        "Status": status,
    }

    properties: Dict[str, Dict] = {}
    for name, value in update_values.items():
        prop_type = property_types.get(name)
        if not prop_type:
            continue
        built = _build_property(value, prop_type)
        if built is not None:
            properties[name] = built
    return properties


def build_tag_update_properties(
    property_types: Optional[Dict[str, str]],
    tag: Optional[str] = None,
    notes: Optional[str] = None,
    iteration: Optional[int] = None,
) -> Dict:
    property_types = property_types or DEFAULT_PROPERTY_TYPES
    updates: Dict[str, Dict] = {}
    if tag is not None and "Tag" in property_types:
        built = _build_property(tag, property_types["Tag"])
        if built is not None:
            updates["Tag"] = built
    if notes is not None and "Notes" in property_types:
        built = _build_property(notes, property_types["Notes"])
        if built is not None:
            updates["Notes"] = built
    if iteration is not None and "Iteration" in property_types:
        updates["Iteration"] = {"number": iteration}
    return updates


def extract_page_values(page: Dict) -> Dict:
    props = page.get("properties", {})
    result: Dict = {"page_id": page.get("id")}
    for name, prop in props.items():
        ptype = prop.get("type")
        if ptype == "title":
            result[name] = prop["title"][0]["plain_text"] if prop.get("title") else ""
        elif ptype == "rich_text":
            result[name] = prop["rich_text"][0]["plain_text"] if prop.get("rich_text") else ""
        elif ptype == "select":
            result[name] = prop["select"]["name"] if prop.get("select") else ""
        elif ptype == "status":
            result[name] = prop["status"]["name"] if prop.get("status") else ""
        elif ptype == "checkbox":
            result[name] = prop.get("checkbox", False)
        elif ptype == "url":
            result[name] = prop.get("url", "")
        elif ptype == "number":
            result[name] = prop.get("number", 0)
        elif ptype == "created_time":
            result[name] = prop.get("created_time", "")
    return result


def database_url(database_id: str) -> str:
    clean_id = database_id.replace("-", "")
    return f"https://www.notion.so/{clean_id}"
