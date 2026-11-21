# Frontend architecture

The frontend is going to be a smaller streamlit app that is going to let our users ask about the policies that thet are woundering, see the answer from Variant A, Variant B or both side by side. It and it will save nothing to the experiment tables, a demo only. 

## Files

- `frontend/app.py` - the page with the question box and the choice of variant
- `frontend/backend.py` - connects to Databricks and sets up the RAg pipeline
- `frontend/components.py` - shows the answer and the chunks it usde
- `app.yaml` - tells Databricks Apps to start `frontend/app.py`
- `requirements.txt` - streamlit and databricks-sdk

`app.yaml`  is in the root of this repo so the app can import  `src/rag.py`. The
app uses the same pipeline as the experiment and we do not change `src/`.

## Flow

```mermaid
flowchart Lr
    A[User question] --> B[app.py] --> C[backend.py] --> D[src/rag.py]
    D -> E[Vector Search + Llama]
     E -> F[components.py] --> G[Answer on the page]
```
