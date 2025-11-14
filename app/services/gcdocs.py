import requests
import getpass

class Session:
    def __init__(self, base_url="https://gcdocs.gc.ca/infc/llisapi.dll/api/v1"):
        self.base_url = base_url
        self.ticket = None
        self.requests_session = requests.Session()

    def login(self, username=None, password=None):
        # If no credentials provided, fall back to console input
        if username is None:
            username = input("Username: ")
        if password is None:
            password = getpass.getpass("Password: ")
            
        response = self.requests_session.post(f"{self.base_url}/auth", data={
            "username": username,
            "password": password
        })
        response.raise_for_status()
        self.ticket = response.json().get("ticket")
        return self.ticket

class GCDocs:
    def __init__(self, session: Session):
        if not session.ticket:
            raise ValueError("Session must be logged in first")
        self.base_url = session.base_url
        self.headers = {"otcsticket": session.ticket}
        self.requests_session = session.requests_session  # reuse session with cookies

    DEFAULT_METADATA = {
        # AI-extracted fields
        "ai_invoice_number": "",
        "ai_invoice_date": "",
        "ai_company_name": "",
        "ai_total_amount": 0.0,
        "ai_processed": False,
        "ai_confidence": 0.0,

        # Human-validated fields
        "human_invoice_number": "",
        "human_invoice_date": "",
        "human_company_name": "",
        "human_total_amount": 0.0,
        "human_validated": False,
        "human_flagged": False,
        "human_notes": ""
    }

    def get_node_info(self, node_id):
        """Get full node information including metadata"""
        url = f"{self.base_url}/nodes/{node_id}"
        r = self.requests_session.get(url, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def sync_gcdocs_nodes_to_sharepoint_minimal(self, sp_tracker: "SharePointTracker", folder_id: int, stream=False):
        nodes = self.list_nodes(folder_id)
        total = len(nodes)
        created = 0
        skipped = 0
        errors = 0

        start_msg = f"Found {total} nodes in folder {folder_id}. Beginning sync..."
        if stream:
            yield start_msg
        else:
            print(start_msg)

        for i, (node_id, node_name) in enumerate(nodes.items(), start=1):
            try:
                # Check if node already exists
                existing = sp_tracker.get_item_by_node_id(node_id)
                if existing:
                    skipped += 1
                    msg = f"[{i}/{total}] Skipped {node_name} (already present)"
                    if stream:
                        yield msg
                    else:
                        print(msg)
                    continue

                # Default metadata
                defaults = getattr(GCDocs, "DEFAULT_METADATA", {
                    "ai_invoice_number": "",
                    "ai_invoice_date": "",
                    "ai_company_name": "",
                    "ai_total_amount": 0.0,
                    "ai_processed": False,
                    "ai_confidence": 0.0,
                    "human_invoice_number": "",
                    "human_invoice_date": "",
                    "human_company_name": "",
                    "human_total_amount": 0.0,
                    "human_validated": False,
                    "human_flagged": False,
                    "human_notes": ""
                })

                # Compose metadata for SharePoint
                sp_metadata = {k: v for k, v in defaults.items()}

                gcdocs_url = f"https://gcdocs.gc.ca/infc/llisapi.dll/app/nodes/{node_id}"

                sp_tracker.create_or_update_item(
                    node_id=node_id,
                    filename=node_name,
                    gcdocs_url=gcdocs_url,
                    metadata=sp_metadata
                )
                created += 1

                msg = f"[{i}/{total}] Created SharePoint item for {node_name}"
                if stream:
                    yield msg
                else:
                    print(msg)

            except Exception as e:
                errors += 1
                msg = f"[{i}/{total}] Error syncing node {node_id} ({node_name}): {str(e)}"
                if stream:
                    yield msg
                else:
                    print(msg)

        summary = (
            f" "
            f"***************************************************"
            f"Sync complete.\n"
            f"  Total nodes:  {total}\n"
            f"  Created:      {created}\n"
            f"  Skipped:      {skipped} (already present)\n"
            f"  Errors:       {errors}"
            f"***************************************************"
        )

        if stream:
            yield summary
        else:
            print(summary)
            return {
                "total": total,
                "created": created,
                "skipped": skipped,
                "errors": errors
            }

    def list_nodes(self, parent_id):
        """List all child nodes in a folder with proper pagination"""
        url = f"{self.base_url}/nodes/{parent_id}/nodes"
        
        all_nodes = {}
        page = 1
        
        while True:
            params = {
                'page': page
            }  # Let the API use its default limit
            
            response = self.requests_session.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if page == 1:
                print(f"API Response keys: {data.keys()}")
                print(f"Paging info: {data.get('paging', 'No paging key')}")
            # Handle different response formats
            if "data" in data:
                nodes = data["data"]
                # Check for pagination info
                paging = data.get("paging", {})
            elif "results" in data:
                nodes = data["results"]
                paging = data.get("paging", {})
            else:
                nodes = data if isinstance(data, list) else []
                paging = {}
            
            # Add nodes from this page
            for node in nodes:
                all_nodes[node["id"]] = node["name"]
            
            # Check if there are more pages
            # Common pagination indicators:
            # - paging.get("next") exists
            # - len(nodes) == limit (full page means might be more)
            # - data.get("total") > len(all_nodes)
            
            has_next = paging.get("next") is not None
            full_page = len(nodes) >= 20  # If we got results, might be more
            total_count = data.get("total") or paging.get("total")
            
            if has_next or (full_page and (not total_count or len(all_nodes) < total_count)):
                page += 1
                print(f"Fetching page {page}... (found {len(all_nodes)} so far)")
            else:
                break
        
        print(f"Total nodes retrieved: {len(all_nodes)}")
        return all_nodes

    def download_file(self, node_id: int, save_path: str):
        url = f"{self.base_url}/nodes/{node_id}/content"
        response = self.requests_session.get(url, headers=self.headers, stream=True)  # Fixed: use self.requests_session
        response.raise_for_status()

        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return save_path