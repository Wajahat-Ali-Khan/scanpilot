import aiofiles
from typing import Dict, Any
import PyPDF2
import docx

class FileProcessor:
    """Real file processing logic - no mocks"""
    
    @staticmethod
    async def extract_text_from_file(file_path: str, mime_type: str) -> str:
        """Extract text content from uploaded file"""
        try:
            if 'pdf' in mime_type.lower():
                return await FileProcessor._extract_from_pdf(file_path)
            elif 'word' in mime_type.lower() or 'docx' in mime_type.lower():
                return await FileProcessor._extract_from_docx(file_path)
            elif 'text' in mime_type.lower():
                return await FileProcessor._extract_from_txt(file_path)
            else:
                raise ValueError(f"Unsupported file type: {mime_type}")
        except Exception as e:
            raise Exception(f"Failed to extract text: {str(e)}")
    
    @staticmethod
    async def _extract_from_pdf(file_path: str) -> str:
        """Extract text from PDF"""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
        except Exception as e:
            raise Exception(f"PDF extraction failed: {str(e)}")
    
    @staticmethod
    async def _extract_from_docx(file_path: str) -> str:
        """Extract text from DOCX"""
        try:
            doc = docx.Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return text.strip()
        except Exception as e:
            raise Exception(f"DOCX extraction failed: {str(e)}")
    
    @staticmethod
    async def _extract_from_txt(file_path: str) -> str:
        """Extract text from TXT file"""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = await f.read()
                return text.strip()
        except Exception as e:
            raise Exception(f"TXT extraction failed: {str(e)}")
    
    @staticmethod
    def analyze_document(text: str) -> Dict[str, Any]:
        """Perform real document analysis"""
        if not text:
            return {
                "word_count": 0,
                "character_count": 0,
                "line_count": 0,
                "quality_issues": ["Document is empty"],
                "readability_score": 0
            }
        
        words = text.split()
        lines = text.split('\n')
        sentences = text.replace('!', '.').replace('?', '.').split('.')
        
        # Calculate metrics
        word_count = len(words)
        char_count = len(text)
        line_count = len(lines)
        avg_word_length = sum(len(word) for word in words) / word_count if word_count > 0 else 0
        avg_sentence_length = word_count / len([s for s in sentences if s.strip()]) if len(sentences) > 0 else 0
        
        # Quality analysis
        quality_issues = []
        if word_count < 50:
            quality_issues.append("Document is very short")
        if avg_word_length < 3:
            quality_issues.append("Words are unusually short")
        if avg_sentence_length > 30:
            quality_issues.append("Sentences are too long - consider breaking them up")
        if avg_sentence_length < 5:
            quality_issues.append("Sentences are too short - consider combining some")
        
        # Simple readability score (0-100)
        readability_score = min(100, max(0, 100 - (avg_sentence_length - 15) * 2))
        
        return {
            "word_count": word_count,
            "character_count": char_count,
            "line_count": line_count,
            "sentence_count": len([s for s in sentences if s.strip()]),
            "average_word_length": round(avg_word_length, 2),
            "average_sentence_length": round(avg_sentence_length, 2),
            "quality_issues": quality_issues if quality_issues else ["No major issues found"],
            "readability_score": round(readability_score, 2)
        }