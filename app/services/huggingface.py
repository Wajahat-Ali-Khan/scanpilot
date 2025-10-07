from openai import AsyncOpenAI
from openai import OpenAIError
from typing import Dict, Any
import json
import re
from app.config import settings

class HuggingFaceService:
    """Service to interact with Hugging Face Inference API via OpenAI SDK"""
    def __init__(self, api_key: str, model_name: str, base_url: str = None):
        self.api_key = api_key
        # Use the async client
        if base_url:
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = AsyncOpenAI(api_key=api_key)
        self.model_name = model_name

    async def query_model(self, text: str) -> dict:
        """Query the model using async OpenAI SDK."""
        try:
            resp = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": text}],
            )
            # Extract content
            content = None
            if resp.choices and resp.choices[0].message:
                content = resp.choices[0].message.content
            return {
                "content": content,
                "raw": resp,
                "status": "ok"
            }
        except OpenAIError as e:
            return {
                "error": str(e),
                "status": "failed"
            }
    
    async def analyze_text(self, text: str) -> Dict[str, Any]:
        """Analyze text and return structured results with guaranteed JSON format"""
        # Create a structured prompt that forces JSON output
        structured_prompt = f"""
        Analyze the following text and provide a structured JSON response with exactly these keys:
        - "analysis": string describing the overall analysis
        - "suggestions": array of strings with specific improvement suggestions
        - "quality_score": integer between 1-10 representing overall quality

        Text to analyze: {text}

        Return ONLY valid JSON without any additional text, markdown, or explanations.
        Example format:
        {{
          "analysis": "The text shows good structure but has some grammatical issues...",
          "suggestions": ["Fix subject-verb agreement", "Improve paragraph transitions", "Add more specific examples"],
          "quality_score": 7
        }}

        Your JSON response:
        """
        
        result = await self.query_model(structured_prompt)
        
        if "error" in result:
            return {
                "status": "error",
                "message": result["error"],
                "analysis": "Analysis failed due to API error",
                "suggestions": [],
                "quality_score": 0
            }

        content = result.get("content", "")
        # Try to extract and parse JSON from the response
        parsed_result = self._extract_and_parse_json(content)

        if parsed_result:
            return {
                "status": "success",
                "analysis": parsed_result.get("analysis", "No analysis provided"),
                "suggestions": parsed_result.get("suggestions", []),
                "quality_score": parsed_result.get("quality_score", 5)
            }
        else:
            # Fallback: use regex extraction if JSON parsing fails
            return self._fallback_analysis(content)
    
    def _extract_and_parse_json(self, content: str) -> Dict[str, Any]:
        """Extract JSON from model response and parse it"""
        try:
            # Try to find JSON pattern in the response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            
            # If no JSON pattern found, try parsing the entire content
            return json.loads(content)
        except (json.JSONDecodeError, AttributeError) as e:
            print(f"JSON parsing failed: {e}")
            print(f"Raw content: {content}")
            return None
    
    def _fallback_analysis(self, content: str) -> Dict[str, Any]:
        """Fallback analysis when JSON parsing fails"""
        # Extract quality score using regex
        quality_score = 5  # default
        score_match = re.search(r'(\d+)/10|score[:\s]*(\d+)', content.lower())
        if score_match:
            quality_score = int(score_match.group(1) or score_match.group(2))
        
        # Extract suggestions
        suggestions = []
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            # Look for lines that seem like suggestions
            if (any(keyword in line.lower() for keyword in ['suggest', 'improve', 'consider', 'recommend', 'should', 'could']) 
                and len(line) > 10 and len(line) < 200):
                # Clean up the suggestion
                suggestion = re.sub(r'^[-\d\.\s]*', '', line)  # Remove numbering
                suggestions.append(suggestion)
        
        # Limit to 5 suggestions
        suggestions = suggestions[:5]
        
        # Use first 200 chars as analysis
        analysis = content[:200] + "..." if len(content) > 200 else content
        
        return {
            "status": "success",
            "analysis": analysis,
            "suggestions": suggestions,
            "quality_score": quality_score
        }

# Global instance
hf_service = HuggingFaceService(settings.HF_API_KEY, settings.HF_MODEL_NAME, settings.HF_BASE_URL)
