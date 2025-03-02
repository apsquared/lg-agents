from typing import Any, Callable, List, Optional, Annotated
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
import operator
from langchain_core.messages import BaseMessage

from agents.tools.searchweb import SearchResult

class College(BaseModel):
    name: str = Field(
        description="Name of the college"
    )
    location: str = Field(
        description="Location of the college"
    )
    description: str = Field(
        description="Brief description of the college"
    )
    acceptance_rate: Optional[str] = Field(
        description="Acceptance rate of the college if available"
    )
    tuition: Optional[str] = Field(
        description="Tuition cost of the college if available"
    )
    enrollment: Optional[str] = Field(
        description="Enrollment of the college(undergraduates) if available"
    )
    dorm_percentage: Optional[str] = Field(
        description="Percentage of students who live in dorms of the college if available"
    )
    sat_scores: Optional[str] = Field(
        description="SAT scores of the college if available"
    )
    programs: Optional[List[str]] = Field(
        description="List of notable programs or majors",
        default=None
    )
    url: Optional[str] = Field(
        description="URL of the college website if available"
    )
    has_missing_fields: bool = False

def colleges_reducer(current: List[College], update: List[College] | None) -> List[College]:
    #print("REDUCER Called")
    if update is None:
        return current
    
    result = current.copy()
    
    # Process each college in the update
    for new_college in update:
        # Check if college with same name exists
        found = False
        for i, existing_college in enumerate(result):
            if existing_college.name == new_college.name:
                # Replace existing college
                result[i] = new_college
                found = True
                break
        
        # Add new college if not found
        if not found:
            result.append(new_college)
    return result
        


class CollegeFinderInput(TypedDict):
    major: Optional[str] = "any"  # Desired major/field of study
    location_preference: Optional[str] = "any"  # Preferred location/region
    max_tuition: Optional[int] = None  # Maximum tuition budget
    min_acceptance_rate: Optional[float] = None  # Minimum acceptance rate
    max_colleges: int = 5  # Number of colleges to find
    search_query: Optional[str] = None  # Constructed search query
    sat_score: Optional[int] = None  # average SAT score

class CollegeFinderState(TypedDict):
    major: Optional[str]  # Desired major/field of study
    location_preference: Optional[str]  # Preferred location/region
    max_tuition: Optional[int] = None  # Maximum tuition budget
    min_acceptance_rate: Optional[float] = None  # Minimum acceptance rate
    max_colleges: int = 5  # Number of colleges to find
    search_query: Optional[str] = None  # Constructed search query
    sat_score: Optional[int] = None  # average SAT score
    search_results: Annotated[List[SearchResult], operator.add]  # Search results
    colleges: Annotated[List[College], colleges_reducer]  # Found colleges matching criteria
    recommendations: Annotated[List[str], operator.add]  # Specific recommendations for the user
    messages: Annotated[List[BaseMessage], operator.add]  # Messages for ToolNode interaction
    data_gathering_attempts: int = 0  # Counter for data gathering attempts
    status_updates: Annotated[List[str], operator.add] = []