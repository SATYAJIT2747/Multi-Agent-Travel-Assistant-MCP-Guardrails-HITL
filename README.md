

TripMate AI is a web-based travel planning assistant that combines live flight status data, web research, weather information, and generative AI to produce a practical trip plan from a natural-language request.

The project is organized around a multi-agent workflow built with LangGraph. Each specialist handles one part of the travel problem before a final agent combines the results into a readable response.

## Development journey

### Phase 1: Direct integrations

The first version established the core travel-planning application:

- FastAPI served the browser interface and travel-planning endpoint.
- LangGraph coordinated the specialist agents in a sequential workflow.
- Gemini generated the itinerary and final travel response.
- AviationStack and Tavily were called through direct Python integrations in the `tools/` directory.
- PostgreSQL persisted LangGraph checkpoints for conversation threads.

This phase proved the main workflow, but each external service was tightly coupled to the application code. Adding or replacing a provider meant changing the backend or a provider-specific helper, and there was no shared tool interface between agents and services. Weather data was not part of the original workflow.

### Phase 1 limitations

The direct-integration design created several constraints:

- Provider-specific logic lived inside the application or local helper modules.
- Tools were harder to discover, test, and reuse independently from the travel graph.
- A new capability, such as weather, required another custom integration path.
- The architecture was less portable to other MCP-compatible clients and servers.

These limitations motivated the move to Model Context Protocol in the second phase.

### Phase 2: MCP-enabled travel workflow

The second version introduces MCP as the tool layer while preserving the working FastAPI and LangGraph foundation. The new `mcp_client.py` configures and loads the external tools independently:

- Tavily is connected through its hosted streamable HTTP MCP endpoint for hotel and destination research.
- AviationStack is launched through `uvx` as a local stdio MCP server for airport and airline information.
- A custom FastMCP weather server was added in `custom_weather_mcp_server.py`.
- The custom weather server calls OpenWeather and exposes `get_current_weather` and `get_forecast` tools.
- The weather specialist extracts the destination, requests current conditions and a forecast, and passes both into itinerary and final-response generation.
- MCP server failures are isolated during tool initialization so one unavailable service does not automatically prevent unrelated MCP tools from loading.

Phase 2 makes the travel assistant more modular and extensible. New tools can be exposed through MCP without embedding every provider implementation directly in the LangGraph workflow.

### Phase 3: Supervisor, guardrails, budget analysis, and human approval

The third version adds control and review layers around the MCP-enabled travel workflow:

- A supervisor agent classifies each request, extracts trip constraints, and selects only the specialist agents needed for that request.
- An input guardrail checks whether the request is travel-related and blocks clearly unrelated or harmful requests before specialist work begins.
- A budget specialist evaluates estimated cost categories, budget risks, feasibility, and money-saving options.
- The itinerary specialist combines the selected specialist results into a draft plan.
- A LangGraph human-in-the-loop interrupt pauses the workflow so a person can approve the draft or provide revision feedback.
- The final response specialist incorporates the approval decision and feedback before generating the polished travel plan.
- LangGraph routing preserves a predictable agent order while skipping specialists that the supervisor did not select.

Phase 3 improves relevance, safety, cost awareness, and user control. Requests no longer have to run every specialist, unrelated prompts are stopped at the workflow boundary, and no final plan is produced until the traveler reviews the draft.

## Architecture

<img width="1536" height="1024" alt="TripMate AI architecture diagram" src="https://github.com/user-attachments/assets/a743e1dc-c2cc-4d82-a754-3e41846766df" />


### Request lifecycle

1. A traveler enters a request such as a destination, duration, origin, and budget in the browser.
2. The browser sends the request to the FastAPI travel endpoint and keeps the returned thread identifier for later requests.
3. The supervisor input guardrail checks whether the request is appropriate for travel planning.
4. For allowed requests, the supervisor extracts trip constraints and chooses the required specialist agents.
5. Selected specialists call the MCP tools for flight, hotel, and weather information, while the budget specialist evaluates trip affordability.
6. The itinerary specialist combines the available results into a practical draft itinerary.
7. LangGraph pauses at the human-in-the-loop interrupt and returns the draft for approval or revision feedback.
8. After approval or feedback, the final specialist produces the polished user-facing answer.
9. LangGraph persists workflow checkpoints in PostgreSQL so a thread can be continued with the same identifier.
10. The API returns the answer and supporting result fields as JSON. The browser renders the Markdown response and can copy or export it as a PDF.

## Agents and responsibilities

| Component | Responsibility |
| --- | --- |
| Supervisor agent | Routes the request, extracts trip constraints, and selects the required specialists. |
| Input guardrail | Allows travel-related requests and blocks clearly unrelated or harmful requests. |
| Flight specialist | Parses route information, resolves cities or countries to IATA codes, and retrieves live flight data. |
| Hotel specialist | Researches hotel options and destination information through web search. |
| Weather specialist | Retrieves current weather and forecast data through the custom weather MCP server. |
| Budget specialist | Estimates trip costs, identifies budget risks, and assesses feasibility. |
| Itinerary specialist | Turns the request and research results into a day-by-day travel plan. |
| Human approval step | Pauses before finalization so a traveler can approve or request revisions. |
| Final response specialist | Produces the structured answer shown to the traveler. |
| PostgreSQL checkpointer | Stores LangGraph state associated with a conversation thread. |

The Phase 3 graph is supervisor-routed. It follows the configured specialist order, but skips agents that are not relevant to the request. The itinerary agent, human approval step, and final response agent remain part of the completion path for allowed requests.

## Tools and services

### LangGraph

LangGraph is the workflow engine. It owns the shared travel state, routes work from the supervisor to selected specialists, pauses for human approval, and connects the workflow to PostgreSQL checkpointing.

### Supervisor and guardrails

The supervisor uses Gemini to perform two control tasks before travel research begins: an input guardrail determines whether the request belongs to the travel domain, and a routing step selects the relevant agents and extracts constraints such as destination, origin, duration, budget, travel style, and preferences. Blocked requests end with a user-facing explanation instead of invoking travel tools.

### Human-in-the-loop approval

The itinerary is generated as a draft and returned through a LangGraph interrupt. The browser can approve the draft or send revision feedback. The same PostgreSQL-backed thread is then resumed so the final response agent can incorporate the review decision.

### Google Gemini

Gemini extracts the destination and is used for language generation when creating the itinerary and composing the final travel response. It does not provide the live flight, weather, or web-search data itself.

### AviationStack

AviationStack supplies airport and airline information through the AviationStack MCP server. It reports operational flight data, not guaranteed ticket prices.

### Tavily

Tavily supplies web-search results for hotel and destination research through its hosted streamable HTTP MCP endpoint. Results are shortened before they are passed into the travel workflow so the final response stays focused.

### Model Context Protocol (MCP)

MCP provides a consistent tool interface between the LangGraph agents and external services. The MCP client in `mcp_client.py` loads each server independently so one unavailable server does not prevent the other tools from being initialized.

| MCP server | Transport | Purpose |
| --- | --- | --- |
| Tavily | Streamable HTTP | Hotel and destination web research. |
| AviationStack | Local stdio | Airport and airline information. Launched with `uvx aviationstack-mcp`. |
| Custom Weather MCP | Local stdio | Current weather and five forecast entries from OpenWeather. Launched with the active Python interpreter and `custom_weather_mcp_server.py`. |

The custom weather server is a FastMCP server with two tools: `get_current_weather` and `get_forecast`.

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
| `mcp_client.py` | MCP server configuration, tool initialization, and MCP calls. |
| `custom_weather_mcp_server.py` | Custom FastMCP server for current weather and forecasts. |
| `tools/flight_tool.py` | Flight route parsing, airport resolution, and AviationStack integration. |
| `tools/tavily_tool.py` | Tavily-backed hotel and destination research. |
| `templates/index.html` | Browser page structure. |
| `static/script.js` | Request handling, result rendering, copy, and PDF actions. |
| `static/style.css` | Browser presentation and responsive layout. |
| `test.py` | Manual end-to-end command-line exercise of the travel workflow. |
| `pyproject.toml` | Project metadata and the `uv` dependency definition. |
| `requirements.txt` | Alternate dependency list for pip or container setup. |
| `Dockerfile.txt` | Container recipe currently included in the repository. |

## Configuration

The application reads credentials and runtime settings from environment variables. Create a local `.env` file with values for:

- `GOOGLE_API_KEY` for Gemini access.
- `AVIATIONSTACK_API_KEY` for live flight data.
- `TAVILY_API_KEY` for hotel and destination research.
- `OPENWEATHER_API_KEY` for the custom weather MCP server.
- `DATABASE_URL` for the PostgreSQL database used by the checkpointer.
- `DEFAULT_ORIGIN_IATA` to change the fallback departure airport. The current default is `DAC`.

Keep credentials out of source control. The repository already ignores `.env` and the local virtual environment.

## Running locally

Install the project dependencies with the repository's `uv` workflow, ensure PostgreSQL and the required environment variables are available, and make sure `uvx` is available for the AviationStack MCP server. Then start the FastAPI application with Uvicorn. Open `http://127.0.0.1:8000` in a browser.

The `/health` endpoint returns a simple service status. The browser uses `/api/travel` to submit requests and receives the answer, thread identifier, flight results, hotel results, itinerary, and model-call count.

## Current limitations and next steps

- Flight information is live/status data; ticket pricing is not guaranteed by the AviationStack integration.
- Hotel suggestions are search results and should be verified before booking.
- The supervisor preserves a configured execution order, so selected specialists still run sequentially rather than in parallel.
- MCP tool availability depends on the hosted Tavily endpoint, `uvx` and the AviationStack MCP package, and the local custom weather server.
- Supervisor and guardrail decisions depend on a valid structured response from the language model; the workflow includes a full-agent fallback when supervisor parsing fails.
- The current guardrail is an input policy check. It does not replace provider verification, booking confirmation, or a separate output safety review.
- The included container file and dependency files should be kept aligned before container deployment.

Future improvements include stronger structured-output validation, an explicit output guardrail, real booking integrations behind approval, and expanded MCP tools.

## License

See [LICENSE](LICENSE).

