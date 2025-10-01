import httpx
from typing import Dict, Any
from app.config import settings

class HuggingFaceService:
    def __init__(self):
        self.api_key = settings.HF_API_KEY
        self.base_url = "https://api-inference.huggingface.co/models"
    
    async def query_model(self, model_name: str, text: str) -> Dict[str, Any]:
        """Query Hugging Face Inference API"""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/{model_name}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json={"inputs": text}
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                return {"error": str(e), "status": "failed"}
    
    async def analyze_text(self, text: str, model_name: str = "google/flan-t5-base") -> Dict[str, Any]:
        """Analyze text and return structured results"""
        # Create a prompt for document analysis
        prompt = f"""Analyze the following text for potential issues, errors, and suggestions:

Text: {text[:1000]}

Provide:
1. Key issues found
2. Suggestions for improvement
3. Overall quality score (1-10)
"""
        
        result = await self.query_model(model_name, prompt)
        
        if "error" in result:
            return {
                "status": "error",
                "message": result["error"],
                "suggestions": []
            }
        
        # Parse the response
        analysis = result[0].get("generated_text", "") if isinstance(result, list) else str(result)
        
        return {
            "status": "success",
            "analysis": analysis,
            "model_used": model_name,
            "suggestions": self._extract_suggestions(analysis),
            "quality_score": self._extract_score(analysis)
        }
    
    def _extract_suggestions(self, text: str) -> list:
        """Extract suggestions from analysis"""
        suggestions = []
        lines = text.split("\n")
        for line in lines:
            if any(keyword in line.lower() for keyword in ["suggest", "improve", "consider", "recommend"]):
                suggestions.append(line.strip())
        return suggestions[:5]  # Return top 5 suggestions
    
    def _extract_score(self, text: str) -> int:
        """Extract quality score from analysis"""
        import re
        match = re.search(r'(\d+)/10|score[:\s]+(\d+)', text.lower())
        if match:
            return int(match.group(1) or match.group(2))
        return 7  # Default score

hf_service = HuggingFaceService()