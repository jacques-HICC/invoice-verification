import os
from typing import List, Dict, Optional

class InvoiceRepository:
    """
    Manages invoice documents with SharePoint tracking
    - Downloads from GCDocs
    - Tracks metadata in SharePoint
    - Updates processing status
    """
    
    def __init__(self, gcdocs, sharepoint_tracker, folder_id: int, download_path: str = "uploads"):
        self.gcdocs = gcdocs
        self.sp_tracker = sharepoint_tracker
        self.folder_id = folder_id
        self.download_path = download_path
        os.makedirs(download_path, exist_ok=True)
    
    def download_new_invoices(self) -> List[str]:
        """
        Download invoices that haven't been AI-processed yet (from SharePoint tracking)
        Returns list of local file paths
        """
        # Get all items from SharePoint
        sp_items = self.sp_tracker.get_all_items()
        
        # Filter for unprocessed
        unprocessed_node_ids = [
            item.get("NodeID") 
            for item in sp_items 
            if not item.get("AI_Processed", False)
        ]
        
        if not unprocessed_node_ids:
            print("No unprocessed invoices found in SharePoint")
            return []
        
        print(f"Found {len(unprocessed_node_ids)} unprocessed invoices")
        
        downloaded_files = []
        
        for node_id in unprocessed_node_ids:
            try:
                # Get filename from SharePoint
                sp_item = self.sp_tracker.get_item_by_node_id(node_id)
                if not sp_item:
                    continue
                
                filename = sp_item.get("Filename", f"unknown_{node_id}.pdf")
                
                # Download the file
                local_path = os.path.join(self.download_path, f"{node_id}_{filename}")
                
                # Skip if already downloaded
                if os.path.exists(local_path):
                    print(f"  Already downloaded: {filename}")
                    downloaded_files.append(local_path)
                    continue
                
                print(f"  Downloading: {filename}")
                self.gcdocs.download_node(node_id, local_path)
                downloaded_files.append(local_path)
                
            except Exception as e:
                print(f"  Error downloading node {node_id}: {e}")
        
        return downloaded_files
    
    def get_node_id_from_filename(self, filename: str) -> Optional[int]:
        """Extract node ID from filename format: {node_id}_{original_name}.pdf"""
        try:
            return int(filename.split('_')[0])
        except (ValueError, IndexError):
            return None
    
    def update_ai_metadata(self, filename: str, extracted_data: Dict, confidence_scores: Dict):
        """
        Update SharePoint with AI extraction results
        """
        node_id = self.get_node_id_from_filename(filename)
        if not node_id:
            raise ValueError(f"Could not extract node_id from filename: {filename}")
        
        success = self.sp_tracker.update_ai_fields(
            node_id,
            extracted_data,
            confidence_scores
        )
        
        if success:
            print(f"✓ Updated SharePoint AI fields for node {node_id}")
        else:
            print(f"✗ Failed to update SharePoint for node {node_id}")
        
        return success
    
    def update_human_metadata(self, filename: str, validated_data: Dict, 
                            flagged: bool = False, notes: str = ""):
        """
        Update SharePoint with human validation results
        """
        node_id = self.get_node_id_from_filename(filename)
        if not node_id:
            raise ValueError(f"Could not extract node_id from filename: {filename}")
        
        success = self.sp_tracker.update_human_fields(
            node_id,
            validated_data,
            flagged,
            notes
        )
        
        if success:
            print(f"✓ Updated SharePoint human validation for node {node_id}")
        else:
            print(f"✗ Failed to update SharePoint for node {node_id}")
        
        return success
    
    def get_all_invoices(self, include_processed: bool = False) -> List[Dict]:
        """
        Get all invoices from SharePoint
        """
        all_items = self.sp_tracker.get_all_items()
        
        if not include_processed:
            # Filter for unprocessed only
            return [item for item in all_items if not item.get("AI_Processed", False)]
        
        return all_items
    
    def get_statistics(self) -> Dict:
        """
        Get processing statistics from SharePoint
        """
        return self.sp_tracker.get_statistics()