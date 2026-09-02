

TripMate AI is a web-based travel planning assistant that combines live flight status data, web research, and generative AI to produce a practical trip plan from a natural-language request.

The project is organized around a multi-agent workflow built with LangGraph. Each specialist handles one part of the travel problem before a final agent combines the results into a readable response.

> **Implementation status:** The current repository contains the FastAPI, LangGraph, flight, hotel-research, Gemini, and PostgreSQL pieces described below. The project name references MCP, guardrails, and human-in-the-loop approval, but dedicated MCP servers, explicit guardrail nodes, and an approval interrupt are not present in the current source yet.

## Architecture

<img width="1536" height="1024" alt="TripMate AI architecture diagram" src="https://github.com/user-attachments/assets/a743e1dc-c2cc-4d82-a754-3e41846766df" />


### Request lifecycle

1. A traveler enters a request such as a destination, duration, origin, and budget in the browser.
2. The browser sends the request to the FastAPI travel endpoint and keeps the returned thread identifier for later requests.
3. The flight specialist interprets locations, resolves them to airport codes, and requests live flight-status information.
4. The hotel specialist sends a destination-focused research query to Tavily and returns concise search results.
5. The itinerary specialist uses the request and gathered travel information to create a practical itinerary with Gemini.
6. The final specialist combines flights, hotel research, itinerary, budget context, and recommendations into the user-facing answer.
7. LangGraph persists workflow checkpoints in PostgreSQL so a thread can be continued with the same identifier.
8. The API returns the final answer and supporting result fields as JSON. The browser renders the Markdown response and can copy or export it as a PDF.

## Agents and responsibilities

| Component | Responsibility |
| --- | --- |
| Flight specialist | Parses route information, resolves cities or countries to IATA codes, and retrieves live flight data. |
| Hotel specialist | Researches hotel options and destination information through web search. |
| Itinerary specialist | Turns the request and research results into a day-by-day travel plan. |
| Final response specialist | Produces the structured answer shown to the traveler. |
| PostgreSQL checkpointer | Stores LangGraph state associated with a conversation thread. |

The current graph is sequential rather than supervisor-routed: flight search runs first, followed by hotel research, itinerary generation, and final response composition.

## Tools and services

### LangGraph

LangGraph is the workflow engine. It owns the shared travel state, executes the specialist stages in order, and connects the workflow to PostgreSQL checkpointing.

### Google Gemini

Gemini is used for language generation in two places: creating the itinerary and composing the final travel response. It does not provide the live flight or web-search data itself.

### AviationStack

AviationStack supplies live flight and status data. The flight tool supports route filters such as origin, destination, or both. It reports operational flight details, not guaranteed ticket prices.

### Tavily

Tavily supplies web-search results for hotel and destination research. Results are shortened before they are passed into the travel workflow so the final response stays focused.

### PostgreSQL and LangGraph Postgres Checkpointer

PostgreSQL stores workflow checkpoints keyed by a thread identifier. This gives the application a durable place to keep LangGraph state across requests and server restarts, provided the database remains available.

### FastAPI and Uvicorn

FastAPI exposes the web page, health check, and travel-planning API. Uvicorn runs the ASGI application locally or in a container.

### Browser presentation layer

The frontend uses Jinja2 for the initial HTML page, plain JavaScript for API calls and interaction, CSS for the interface, Marked for Markdown rendering, and html2pdf.js for PDF export.

## Repository layout

| Path | Purpose |
| --- | --- |
| `app.py` | FastAPI application and HTTP endpoints. |
| `backend.py` | LangGraph state, agents, model calls, and PostgreSQL checkpointing. |
| `tools/flight_tool.py` | Flight route parsing, airport resolution, and AviationStack integration. |
| `tools/tavily_tool.py` | Tavily-backed hotel and destination research. |
| `templates/index.html` | Browser page structure. |
| `static/script.js` | Request handling, result rendering, copy, and PDF actions. |
| `static/style.css` | Browser presentation and responsive layout. |
| `test.py` | Manual end-to-end command-line exercise of the travel workflow. |
| `pyproject.toml` | Project metadata and the `uv` dependency definition. |
| `requirement.txt` | Alternate dependency list for pip or container setup. |
| `Dockerfile.txt` | Container recipe currently included in the repository. |

## Configuration

The application reads credentials and runtime settings from environment variables. Create a local `.env` file with values for:

- `GOOGLE_API_KEY` for Gemini access.
- `AVIATIONSTACK_API_KEY` for live flight data.
- `TAVILY_API_KEY` for hotel and destination research.
- `DATABASE_URL` for the PostgreSQL database used by the checkpointer.
- `DEFAULT_ORIGIN_IATA` to change the fallback departure airport. The current default is `DAC`.

Keep credentials out of source control. The repository already ignores `.env` and the local virtual environment.

## Running locally

Install the project dependencies with the repository's `uv` workflow, ensure PostgreSQL and the required environment variables are available, then start the FastAPI application with Uvicorn. Open `http://127.0.0.1:8000` in a browser.

The `/health` endpoint returns a simple service status. The browser uses `/api/travel` to submit requests and receives the answer, thread identifier, flight results, hotel results, itinerary, and model-call count.

## Limitations and next architectural steps

- Flight information is live/status data; ticket pricing is not guaranteed by the AviationStack integration.
- Hotel suggestions are search results and should be verified before booking.
- The workflow currently runs specialist stages in a fixed sequence.
- MCP tool servers are not yet wired into the graph; the integrations are direct Python/API calls.
- Guardrail policy checks and human approval are not yet represented as graph nodes or interrupts.
- The included container file expects `requirements.txt`, while this repository currently provides `requirement.txt` and `pyproject.toml`; container deployment should align those names before use.

The natural next evolution is to place the external integrations behind MCP servers, add input and output guardrail stages around the graph, and introduce a human approval checkpoint before any future booking or other consequential action.

## License

See [LICENSE](LICENSE).

