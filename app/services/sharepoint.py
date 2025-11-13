import requests
from azure.identity import InteractiveBrowserCredential
from typing import Dict, List, Optional

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

class SharePointTracker:
    def __init__(self, site_name: str, list_name: str, tenant_name: str):
        """
        :param site_name: The SharePoint site name (e.g., "DataScience")
        :param list_name: The SharePoint list name (e.g., "invoice-verification-tracking")
        :param tenant_name: Your tenant domain (e.g., "142gc.sharepoint.com")
        """
        self.site_name = site_name
        self.list_name = list_name
        self.tenant_name = tenant_name
        self.credential = None
        self.access_token = None
        self.site_id = None
        self.list_id = None
        self.headers = None

    def login(self):
        # Interactive browser login with MFA
        self.credential = InteractiveBrowserCredential()
        token = self.credential.get_token("https://graph.microsoft.com/.default")
        self.access_token = token.token
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        # Resolve site ID
        site_url = f"{GRAPH_BASE_URL}/sites/{self.tenant_name}:/sites/{self.site_name}"
        r = requests.get(site_url, headers=self.headers)
        r.raise_for_status()
        self.site_id = r.json()["id"]

        # Resolve list ID
        lists_url = f"{GRAPH_BASE_URL}/sites/{self.site_id}/lists"
        r = requests.get(lists_url, headers=self.headers)
        r.raise_for_status()
        lists = r.json().get("value", [])
        for lst in lists:
            if lst["name"] == self.list_name:
                self.list_id = lst["id"]
                break
        if not self.list_id:
            raise ValueError(f"List '{self.list_name}' not found on site '{self.site_name}'")
        print(f"✓ Logged in and connected to SharePoint list: {self.list_name}")

    def get_all_items(self) -> List[Dict]:
        url = f"{GRAPH_BASE_URL}/sites/{self.site_id}/lists/{self.list_id}/items?expand=fields"
        r = requests.get(url, headers=self.headers)
        r.raise_for_status()
        items = r.json().get("value", [])
        return [item["fields"] for item in items]

    def get_item_by_node_id(self, node_id: int) -> Optional[Dict]:
        all_items = self.get_all_items()
        node_id_str = str(node_id)
        for item in all_items:
            if str(item.get("NodeID")) == node_id_str:
                return item
        return None

    def create_or_update_item(self, node_id: int, filename: str, gcdocs_url: str, metadata: Dict = None):
        if metadata is None:
            metadata = {}
        print(f"🔍 DEBUG: Metadata received: {metadata}")
        fields = {
            "NodeID": str(node_id),
            "Filename": filename,
            "GCDocsURL": gcdocs_url,
            "AI_InvoiceNumber": metadata.get("ai_invoice_number", ""),
            "AI_InvoiceDate": metadata.get("ai_invoice_date", ""),
            "AI_CompanyName": metadata.get("ai_company_name", ""),
            "AI_TotalAmount": float(metadata.get("ai_total_amount", 0)),
            "AI_Processed": bool(metadata.get("ai_processed", False)),
            "AI_Confidence": float(metadata.get("ai_confidence", 0)),
            "Human_InvoiceNumber": metadata.get("human_invoice_number", ""),
            "Human_InvoiceDate": metadata.get("human_invoice_date", ""),
            "Human_CompanyName": metadata.get("human_company_name", ""),
            "Human_TotalAmount": float(metadata.get("human_total_amount", 0)),
            "Human_Validated": bool(metadata.get("human_validated", False)),
            "Human_Flagged": bool(metadata.get("human_flagged", False)),
            "Human_Notes": metadata.get("human_notes", "")
        }
        print(f"🔍 DEBUG: Fields to send to SharePoint: {fields}")
        # Check if item exists
        existing_item = self.get_item_by_node_id(node_id)
        if existing_item:
            # Update item
            item_id = existing_item.get("id")
            url = f"{GRAPH_BASE_URL}/sites/{self.site_id}/lists/{self.list_id}/items/{item_id}/fields"
            r = requests.patch(url, headers=self.headers, json=fields)
            print(f"🔍 DEBUG: PATCH response status: {r.status_code}")
            print(f"🔍 DEBUG: PATCH response body: {r.text}")
            r.raise_for_status()
            print(f"✓ Updated SharePoint item for NodeID {node_id}")
        else:
            # Create item
            url = f"{GRAPH_BASE_URL}/sites/{self.site_id}/lists/{self.list_id}/items"
            r = requests.post(url, headers=self.headers, json={"fields": fields})
            r.raise_for_status()
            print(f"✓ Created SharePoint item for NodeID {node_id}")
