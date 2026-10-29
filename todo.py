from fastapi import FastAPI, HTTPException, Request
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse


import time


app = FastAPI(
    title="Clef task System",
    description="clefing everyday life",
    version="1.0.0",
)

   
class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    status: TaskStatus = TaskStatus.pending


class CreateTask(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    status: TaskStatus = TaskStatus.pending


class UpdateTask(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None


class Task(TaskBase):
    id: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Tasks(BaseModel):
    tasks: list[Task]


class Response(BaseModel):
    message: str
    has_error: bool = False
    error_message: Optional[str] = None
    data: Optional[Task | Tasks] = None

tasks: dict[int, Task] = {}



RATE_LIMIT = 30
TIME_WINDOW = 60


request_counts = {}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = (
        request.client.host
        if request.client
        else "unknown"
    )

    current_time = time.monotonic()


    record = request_counts.get(client_ip)

    if record is None or current_time - record["start"] >= TIME_WINDOW:
        record = {
            "start": current_time,
            "count": 0
        }
        request_counts[client_ip] = record

    if record["count"] >= RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={
                "message": "Too many requests. Please try again later.",
                "has_error": True,
                "error_message": "Rate limit exceeded",
                "data": None
            },
            headers={
                "Retry-After": str(
                    max(
                        1,
                        int(TIME_WINDOW - (current_time - record["start"]))
                    )
                )
            }
        )

    # Count this request
    record["count"] += 1

    response = await call_next(request)
    return response


next_task_id = 1

@app.get("/")
def home():
    return {"message": "Welcome to the Task Tracker API"}

@app.post("/tasks", response_model=Response, status_code=201)
def create_task(task_data: CreateTask):
    global next_task_id

    new_task = Task(
        id=next_task_id,
        title=task_data.title,
        description=task_data.description,
        status=task_data.status,
        created_at=datetime.now(timezone.utc)
    )

    tasks[next_task_id] = new_task
    next_task_id += 1

    return Response(
        message="Task created successfully",
        has_error=False,
        data=new_task
    )


@app.get("/tasks", response_model=Response)
def get_tasks(
    status: Optional[TaskStatus] = None,
    sort: Optional[str] = None,
    page: int = 1,
    limit: int = 10
):
    if page < 1 or limit < 1:
        raise HTTPException(
            status_code=400,
            detail="Page and limit must be greater than 0"
        )

    if sort not in (None, "created_at"):
        raise HTTPException(
            status_code=400,
            detail="Sort must be 'created_at'"
        )

    
    result = list(tasks.values())

    
    if status is not None:
        result = [task for task in result if task.status == status]

    
    if sort == "created_at":
        result.sort(key=lambda task: task.created_at)

    
    start = (page - 1) * limit
    end = start + limit
    paginated_tasks = result[start:end]

    return Response(
        message="Tasks retrieved successfully",
        has_error=False,
        data=Tasks(tasks=paginated_tasks)
    )


@app.get("/tasks/{task_id}", response_model=Response)
def get_task(task_id: int):
    task = tasks.get(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task with ID {task_id} was not found"
        )

    return Response(
        message="Task retrieved successfully",
        has_error=False,
        data=task
    )



@app.put("/tasks/{task_id}", response_model=Response)
def update_task(task_id: int, task_data: UpdateTask):
    task = tasks.get(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task with ID {task_id} was not found"
        )

    update_data = task_data.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update"
        )

    if "title" in update_data:
        title = update_data["title"]

        if title is None or not title.strip():
            raise HTTPException(
                status_code=400,
                detail="Title cannot be empty"
            )

        update_data["title"] = title.strip()

    if "description" in update_data:
        if update_data["description"] is None:
            raise HTTPException(
                status_code=400,
                detail="Description cannot be null"
            )

    updated_task = task.model_copy(update=update_data)
    tasks[task_id] = updated_task

    return Response(
        message="Task updated successfully",
        has_error=False,
        data=updated_task
    )


@app.delete("/tasks", response_model=Response)
def delete_all_tasks():
    if not tasks:
        return Response(
            message="There are no tasks to delete",
            has_error=False,
            data=Tasks(tasks=[])
        )

    tasks.clear()

    return Response(
        message="All tasks deleted successfully",
        has_error=False,
        data=Tasks(tasks=[])
    )


@app.delete("/tasks/{task_id}", response_model=Response)
def delete_task(task_id: int):
    task = tasks.get(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task with ID {task_id} was not found"
        )

    del tasks[task_id]

    return Response(
        message=f"Task {task_id} deleted successfully",
        has_error=False,
        data=task
    )
