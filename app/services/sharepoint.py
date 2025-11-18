import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from azure.identity import InteractiveBrowserCredential
from typing import Dict, List, Optional
import time
from datetime import datetime, timedelta

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

class SharePointTracker:
    def __init__(self, site_name: str, list_name: str, tenant_name: str):
        self.site_name = site_name
        self.list_name = list_name
        self.tenant_name = tenant_name
        
        # Auth State
        self.credential = None
        self.token_object = None
        self.token_expires_at = datetime.now()
        self.site_id = None
        self.list_id = None
        
        # --- NETWORK SETUP ---
        self.session = requests.Session()
        
        # Aggressive Retry Strategy
        retries = Retry(
            total=5,
            backoff_factor=5,  # Wait 5s, 10s, 20s, 40s... (Slower backoff for stability)
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PATCH", "PUT"]
        )
        
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _ensure_valid_token(self):
        """Refreshes token if it is expired or close to expiring"""
        if not self.token_object or datetime.now() >= (self.token_expires_at - timedelta(minutes=5)):
            print("🔄 Refreshing SharePoint Access Token...")
            if not self.credential:
                self.credential = InteractiveBrowserCredential()
            
            # Get new token
            self.token_object = self.credential.get_token("https://graph.microsoft.com/.default")
            
            # Calculate expiry (default to 1 hour if not specified)
            # AccessToken objects usually have an 'expires_on' timestamp
            if hasattr(self.token_object, 'expires_on'):
                 self.token_expires_at = datetime.fromtimestamp(self.token_object.expires_on)
            else:
                 self.token_expires_at = datetime.now() + timedelta(hours=1)

            # Update Session Headers
            self.session.headers.update({
                "Authorization": f"Bearer {self.token_object.token}",
                "Content-Type": "application/json",
                "Prefer": "honor-throttling" # Tell Graph we respect Retry-After headers
            })
            print("✓ Token Refreshed")

    def login(self):
        self._ensure_valid_token()

        # Resolve site ID
        site_url = f"{GRAPH_BASE_URL}/sites/{self.tenant_name}:/sites/{self.site_name}"
        r = self.session.get(site_url, timeout=30)
        r.raise_for_status()
        self.site_id = r.json()["id"]

        # Resolve list ID
        lists_url = f"{GRAPH_BASE_URL}/sites/{self.site_id}/lists"
        r = self.session.get(lists_url, timeout=30)
        r.raise_for_status()
        lists = r.json().get("value", [])
        for lst in lists:
            if lst["name"] == self.list_name:
                self.list_id = lst["id"]
                break
        if not self.list_id:
            raise ValueError(f"List '{self.list_name}' not found on site '{self.site_name}'")
        print(f"✓ Connected to SharePoint List: {self.list_name}")

    def get_all_items(self) -> List[Dict]:
        """Fallback method: downloads everything. Use sparingly."""
        self._ensure_valid_token()
        url = f"{GRAPH_BASE_URL}/sites/{self.site_id}/lists/{self.list_id}/items?expand=fields"
        r = self.session.get(url, timeout=60)
        r.raise_for_status()
        items = r.json().get("value", [])
        return [item["fields"] for item in items]

    def get_item_by_node_id(self, node_id: int) -> Optional[Dict]:
        """
        Optimized lookup using OData Filter.
        Instead of downloading the whole list, asks specifically for this NodeID.
        """
        self._ensure_valid_token()
        node_id_str = str(node_id)

        # OPTIMIZATION: Try filtering server-side first
        # Syntax: items?expand=fields&$filter=fields/NodeID eq '12345'
        try:
            filter_url = (
                f"{GRAPH_BASE_URL}/sites/{self.site_id}/lists/{self.list_id}/items"
                f"?expand=fields&$filter=fields/NodeID eq '{node_id_str}'"
            )
            r = self.session.get(filter_url, timeout=20)
            
            # If 400 Bad Request, it likely means the column isn't indexed.
            # In that case, we catch the error and fall back to the slow method.
            if r.status_code == 400:
                raise Exception("Column not indexed")
                
            r.raise_for_status()
            data = r.json()
            
            if data.get("value"):
                # Item found!
                return data["value"][0]["fields"]
            else:
                # Item not found (list is empty for this filter)
                return None

        except Exception as e:
            # FALLBACK: If filtering fails (e.g. NodeID not indexed in SharePoint),
            # we must do the slow crawl.
            # print(f"⚠️ Filter lookup failed ({e}). Falling back to full list scan...")
            all_items = self.get_all_items()
            for item in all_items:
                if str(item.get("NodeID")) == node_id_str:
                    return item
            return None

    def create_or_update_item(self, node_id: int, filename: str, gcdocs_url: str, metadata: Dict = None):
        self._ensure_valid_token()
        
        if metadata is None:
            metadata = {}
        
        # Ensure no NaNs (SharePoint hates NaN)
        def clean_float(val):
            try:
                import math
                f = float(val)
                if math.isnan(f) or math.isinf(f): return 0.0
                return f
            except: return 0.0

        fields = {
            "NodeID": str(node_id),
            "Filename": filename,
            "GCDocsURL": gcdocs_url,
            "AI_InvoiceNumber": metadata.get("ai_invoice_number", ""),
            "AI_InvoiceDate": metadata.get("ai_invoice_date", ""),
            "AI_CompanyName": metadata.get("ai_company_name", ""),
            "AI_TotalAmount": clean_float(metadata.get("ai_total_amount", 0)),
            "AI_Processed": bool(metadata.get("ai_processed", False)),
            "AI_Confidence": clean_float(metadata.get("ai_confidence", 0)),
            "OCR_Method": metadata.get("ocr_method", ""),
            "LLM_Used": metadata.get("llm_used", ""),
            "Time_Taken": clean_float(metadata.get("time_taken", 0)),
            "Human_InvoiceNumber": metadata.get("human_invoice_number", ""),
            "Human_InvoiceDate": metadata.get("human_invoice_date", ""),
            "Human_CompanyName": metadata.get("human_company_name", ""),
            "Human_TotalAmount": clean_float(metadata.get("human_total_amount", 0)),
            "Human_Validated": bool(metadata.get("human_validated", False)),
            "Human_Flagged": bool(metadata.get("human_flagged", False)),
            "Human_Notes": metadata.get("human_notes", "")
        }
        
        # Check if item exists
        existing_item = self.get_item_by_node_id(node_id)
        
        try:
            if existing_item:
                # Update
                item_id = existing_item.get("id")
                url = f"{GRAPH_BASE_URL}/sites/{self.site_id}/lists/{self.list_id}/items/{item_id}/fields"
                r = self.session.patch(url, json=fields, timeout=30)
                r.raise_for_status()
                print(f"✓ Updated SharePoint item for NodeID {node_id}")
            else:
                # Create
                url = f"{GRAPH_BASE_URL}/sites/{self.site_id}/lists/{self.list_id}/items"
                r = self.session.post(url, json={"fields": fields}, timeout=30)
                r.raise_for_status()
                print(f"✓ Created SharePoint item for NodeID {node_id}")
                
        except requests.exceptions.RetryError:
            print(f"❌ Max retries exceeded for NodeID {node_id}. Network is unstable.")
            raise
        except Exception as e:
            print(f"❌ Error syncing NodeID {node_id}: {str(e)}")
            raise