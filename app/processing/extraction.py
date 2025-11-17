from llama_cpp import Llama
import json
from pathlib import Path
from json_repair import repair_json

from config import AIConfig

class LLMExtractor:
    def __init__(self, model_filename: str = None):
        # Use config values
        n_ctx = AIConfig.CTX_SIZE
        model_filename = model_filename or AIConfig.MODEL_PATH

        # Absolute path to app/models
        app_root = Path(__file__).resolve().parent.parent
        models_dir = app_root / 'models'
        model_path = models_dir / model_filename

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at: {model_path}")

        self.n_ctx = n_ctx
        self.model_name = model_filename

        print(f"Loading model from: {model_path}")
        self.llm = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=4,
            n_gpu_layers=0,
            verbose=False
        )
        self.model_name = model_filename
    
    def extract_invoice_data(self, ocr_result) -> dict:
        """
        Extract structured data from invoice OCR result.
        
        Args:
            ocr_result: Dictionary containing OCR results with structure:
                {
                    "method": str,
                    "full_text": str,
                    "pages": [...],
                    "total_pages": int
                }
                OR a string (for backward compatibility)
        """
        # Handle different input types
        if isinstance(ocr_result, dict):
            ocr_text = ocr_result.get("full_text", "")
            ocr_method = ocr_result.get("method", "unknown")
            print(f"📊 Using OCR method: {ocr_method}")
        elif isinstance(ocr_result, list):
            # If it's a list, try to extract text from it (maybe it's a list of page results)
            print("⚠️ Warning: OCR result is a list, attempting to extract text...")
            ocr_text = ""
            for item in ocr_result:
                if isinstance(item, dict):
                    ocr_text += item.get("text", "") + "\n"
                elif isinstance(item, str):
                    ocr_text += item + "\n"
            ocr_method = "list_format"
            print(f"📊 Extracted {len(ocr_text)} chars from list")
        elif isinstance(ocr_result, str):
            # Backward compatibility if plain text is passed
            ocr_text = ocr_result
            ocr_method = "legacy"
        else:
            print(f"❌ Unexpected OCR result type: {type(ocr_result)}")
            return {
                "invoice_number": "",
                "company_name": "",
                "invoice_date": "",
                "total_amount": 0.0,
                "confidence": 0.0,
                "model_used": self.model_name,
                "ocr_method": "error",
                "error": f"Unexpected OCR result type: {type(ocr_result)}"
            }
        
        # Make sure we have actual text
        if not ocr_text or len(ocr_text.strip()) < 10:
            print("⚠️ Warning: No text or insufficient text extracted from OCR result")
            return {
                "invoice_number": "",
                "company_name": "",
                "invoice_date": "",
                "total_amount": 0.0,
                "confidence": 0.0,
                "model_used": self.model_name,
                "ocr_method": ocr_method if isinstance(ocr_result, dict) else "legacy",
                "error": "No text content in OCR result"
            }

        # Debug: print first 500 chars of OCR text
        print(f"📝 OCR Text Preview (first 500 chars):\n{ocr_text[:500]}\n")
        print(f"📊 Total OCR text length: {len(ocr_text)} chars")

        # Slice header and footer for context - but ensure they're not empty
        header_slice = ocr_text[:min(1200, len(ocr_text))]
        footer_slice = ocr_text[-min(800, len(ocr_text)):] if len(ocr_text) > 800 else ocr_text

        # Clean up the text - remove excessive dashes/lines that might confuse the model
        def clean_text(text):
            lines = text.split('\n')
            cleaned_lines = []
            for line in lines:
                # Skip lines that are mostly dashes or equal signs
                if len(line.strip()) > 0 and not (line.count('-') > len(line) * 0.8 or line.count('=') > len(line) * 0.8):
                    cleaned_lines.append(line)
            return '\n'.join(cleaned_lines)
        
        header_slice = clean_text(header_slice)
        footer_slice = clean_text(footer_slice)

        # prompt from AIConfig class in config.py
        prompt = AIConfig.INVOICE_EXTRACTION_PROMPT.format(
            header_slice=header_slice,
            footer_slice=footer_slice
        )

        print(f"📤 Sending prompt to LLM ({len(prompt)} chars)")
                    
        response = self.llm(
            prompt,
            max_tokens=AIConfig.MAX_TOKENS,
            temperature=AIConfig.TEMPERATURE,
            stop=["INVOICE TEXT:", "Your task:", "\n\n\n"],
            echo=False
        )
        
        output_text = response['choices'][0]['text'].strip()
        print(f"🔍 RAW LLM OUTPUT ({len(output_text)} chars): {output_text[:500]}")

        # If output is all dashes or garbage, try again with simpler prompt
        if not output_text or len(output_text) < 10 or output_text.count('-') > len(output_text) * 0.5:
            print("⚠️ LLM output is unusable, trying simplified prompt...")
            
            simple_prompt = f"""Extract invoice data from this text and return JSON only:

{ocr_text[:2000]}

Return JSON format:
{{"invoice_number": "", "company_name": "", "invoice_date": "", "total_amount": 0.0}}

JSON:"""
            
            response = self.llm(
                simple_prompt,
                max_tokens=200,
                temperature=0.1,
                stop=["\n\n"],
                echo=False
            )
            output_text = response['choices'][0]['text'].strip()
            print(f"🔍 RETRY OUTPUT: {output_text[:500]}")

        try:
            # Remove markdown fences if present
            if "```json" in output_text:
                output_text = output_text.split("```json")[1].split("```")[0].strip()
            elif "```" in output_text:
                output_text = output_text.split("```")[1].split("```")[0].strip()
            
            # Try to find JSON object in the output
            if '{' in output_text and '}' in output_text:
                start_idx = output_text.find('{')
                end_idx = output_text.rfind('}') + 1
                output_text = output_text[start_idx:end_idx]
            
            print(f"🔧 Cleaned output for parsing: {output_text}")
            
            # Repair common JSON issues
            repaired = repair_json(output_text)
            print(f"🔍 REPAIRED JSON: {repaired}")
            
            data = json.loads(repaired)

            # Clean numeric fields
            try:
                raw_amount = str(data.get('total_amount', 0))
                clean_amount = raw_amount.replace(",", "").replace("$", "").strip()
                data['total_amount'] = float(clean_amount)
            except (ValueError, TypeError):
                data['total_amount'] = 0.0
            
            # Add metadata
            data['confidence'] = 0.85
            data['model_used'] = self.model_name
            data['ocr_method'] = ocr_method
            
            print(f"✅ Successfully extracted: {data}")
            return data
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON Parse Error: {str(e)}")
            print(f"❌ Failed to parse output: {output_text[:200]}")
            
            # Safely get ocr_method
            if isinstance(ocr_result, dict):
                ocr_method = ocr_result.get("method", "unknown")
            elif isinstance(ocr_result, list):
                ocr_method = "list_format"
            else:
                ocr_method = "legacy"
            
            return {
                "invoice_number": "",
                "company_name": "",
                "invoice_date": "",
                "total_amount": 0.0,
                "confidence": 0.0,
                "model_used": self.model_name,
                "ocr_method": ocr_method,
                "error": f"Failed to parse: {str(e)}"
            }
    
    def extract_invoice_data_from_blocks(self, ocr_result: dict) -> dict:
        """
        Alternative method that leverages the structured block data from PaddleOCR.
        Useful if you want to use bounding boxes and confidence scores.
        """
        if not isinstance(ocr_result, dict) or ocr_result.get("method") != "paddleocr":
            # Fall back to regular extraction
            return self.extract_invoice_data(ocr_result)
        
        # Build a structured prompt using block information
        pages = ocr_result.get("pages", [])
        
        # Collect high-confidence blocks
        important_blocks = []
        for page in pages:
            for block in page.get("blocks", []):
                if block.get("confidence", 0) > 0.7:  # High confidence threshold
                    important_blocks.append(block["text"])
        
        # Combine with full text approach
        full_text = ocr_result.get("full_text", "")
        
        # Use only high-confidence text for better accuracy
        high_conf_text = "\n".join(important_blocks[:30])  # Top 30 high-confidence blocks
        
        enhanced_prompt = f"""Extract invoice details from this OCR text.

TEXT:
{high_conf_text}

Return ONLY a JSON object:
{{"invoice_number": "", "company_name": "", "invoice_date": "", "total_amount": 0.0}}

JSON:"""

        response = self.llm(
            enhanced_prompt,
            max_tokens=200,
            temperature=0.1,
            stop=["\n\n"],
            echo=False
        )
        
        output_text = response['choices'][0]['text'].strip()
        
        # parsing
        try:
            if "```json" in output_text:
                output_text = output_text.split("```json")[1].split("```")[0].strip()
            elif "```" in output_text:
                output_text = output_text.split("```")[1].split("```")[0].strip()
            
            # Try to find JSON object
            if '{' in output_text and '}' in output_text:
                start_idx = output_text.find('{')
                end_idx = output_text.rfind('}') + 1
                output_text = output_text[start_idx:end_idx]
            
            repaired = repair_json(output_text)
            data = json.loads(repaired)
            
            # Clean numeric fields
            try:
                raw_amount = str(data.get('total_amount', 0))
                clean_amount = raw_amount.replace(",", "").replace("$", "").strip()
                data['total_amount'] = float(clean_amount)
            except (ValueError, TypeError):
                data['total_amount'] = 0.0
            
            data['confidence'] = 0.90  # Higher confidence with block-based extraction
            data['model_used'] = self.model_name
            data['ocr_method'] = "paddleocr_blocks"
            
            return data
            
        except json.JSONDecodeError as e:
            return {
                "invoice_number": "",
                "company_name": "",
                "invoice_date": "",
                "total_amount": 0.0,
                "confidence": 0.0,
                "model_used": self.model_name,
                "ocr_method": "paddleocr_blocks",
                "error": f"Failed to parse: {str(e)}"
            }