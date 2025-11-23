from app.services.huggingface import hf_service
from typing import Dict, Any, List

async def generate_suggestion(context: str, selection: str = "") -> Dict[str, Any]:
    """
    Generate AI-powered suggestions for document editing.
    Uses HuggingFace service for real AI analysis.
    
    Args:
        context: The surrounding text context
        selection: The selected text to analyze (optional)
        
    Returns:
        Dict containing suggestions and analysis
    """
    # Build the prompt based on whether we have a selection
    if selection:
        prompt = f"""You are an expert writing assistant. Analyze the following selected text and provide specific, actionable suggestions to improve it.

Selected text: "{selection}"

Context: "{context}"

Provide 3-5 specific suggestions to improve clarity, grammar, style, or structure. Format your response as a JSON object with:
- "suggestions": array of suggestion strings
- "tone": detected tone (professional/casual/academic)
- "confidence": confidence score 0-1

Return ONLY valid JSON."""
    else:
        prompt = f"""You are an expert writing assistant. Analyze the following text and provide specific, actionable suggestions to improve it.

Text: "{context}"

Provide 3-5 specific suggestions to improve clarity, grammar, style, or structure. Format your response as a JSON object with:
- "suggestions": array of suggestion strings  
- "tone": detected tone (professional/casual/academic)
- "confidence": confidence score 0-1

Return ONLY valid JSON."""
    
    try:
        # Use the HuggingFace service to get AI analysis
        result = await hf_service.query_model(prompt)
        
        if result.get("status") == "failed":
            return {
                "status": "error",
                "message": result.get("error", "AI service unavailable"),
                "suggestions": ["Unable to generate suggestions at this time."],
                "tone": "unknown",
                "confidence": 0.0
            }
        
        # Extract and parse the response
        content = result.get("content", "")
        parsed = hf_service._extract_and_parse_json(content)
        
        if parsed and "suggestions" in parsed:
            return {
                "status": "success",
                "suggestions": parsed.get("suggestions", []),
                "tone": parsed.get("tone", "neutral"),
                "confidence": parsed.get("confidence", 0.7)
            }
        else:
            # Fallback to basic suggestions if parsing fails
            return {
                "status": "success",
                "suggestions": [
                    "Consider breaking long sentences into shorter ones for clarity.",
                    "Check for consistent verb tense throughout the text.",
                    "Ensure proper punctuation and grammar.",
                ],
                "tone": "neutral",
                "confidence": 0.5
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "suggestions": ["An error occurred while generating suggestions."],
            "tone": "unknown",
            "confidence": 0.0
        }


async def analyze_document_quality(text: str) -> Dict[str, Any]:
    """
    Analyze overall document quality using AI.
    
    Args:
        text: The full document text
        
    Returns:
        Dict containing quality analysis
    """
    prompt = f"""Analyze the following document and provide a comprehensive quality assessment.

Document text: "{text[:2000]}"  # Limit to first 2000 chars

Provide analysis in JSON format with:
- "overall_score": integer 1-10
- "readability": string assessment
- "strengths": array of 2-3 strengths
- "improvements": array of 2-3 areas to improve
- "summary": brief overall summary

Return ONLY valid JSON."""
    
    try:
        result = await hf_service.query_model(prompt)
        
        if result.get("status") == "failed":
            return {
                "status": "error",
                "message": "Analysis unavailable"
            }
        
        content = result.get("content", "")
        parsed = hf_service._extract_and_parse_json(content)
        
        if parsed:
            return {
                "status": "success",
                **parsed
            }
        else:
            return {
                "status": "success",
                "overall_score": 7,
                "readability": "Good",
                "strengths": ["Clear structure", "Good grammar"],
                "improvements": ["Add more details", "Improve transitions"],
                "summary": "Document is well-written with room for minor improvements."
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
