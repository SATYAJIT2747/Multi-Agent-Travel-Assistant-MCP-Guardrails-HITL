

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

> **Current status:** MCP integration and the OpenWeather custom tool are implemented. Explicit guardrail nodes and a human-in-the-loop approval interrupt are planned for the next phase.

## Architecture

<img width="1536" height="1024" alt="TripMate AI architecture diagram" src="https://github.com/user-attachments/assets/a743e1dc-c2cc-4d82-a754-3e41846766df" />


### Request lifecycle

1. A traveler enters a request such as a destination, duration, origin, and budget in the browser.
2. The browser sends the request to the FastAPI travel endpoint and keeps the returned thread identifier for later requests.
3. The flight specialist calls the AviationStack MCP server to retrieve airport and airline information.
4. The hotel specialist calls the hosted Tavily MCP server with a destination-focused research query.
5. The weather specialist extracts the destination and calls the custom weather MCP server for current conditions and a forecast from OpenWeather.
6. The itinerary specialist uses the request and gathered travel information to create a practical itinerary with Gemini.
7. The final specialist combines flights, hotel research, weather, itinerary, budget context, and recommendations into the user-facing answer.
8. LangGraph persists workflow checkpoints in PostgreSQL so a thread can be continued with the same identifier.
9. The API returns the final answer and supporting result fields as JSON. The browser renders the Markdown response and can copy or export it as a PDF.

## Agents and responsibilities

| Component | Responsibility |
| --- | --- |
| Flight specialist | Parses route information, resolves cities or countries to IATA codes, and retrieves live flight data. |
| Hotel specialist | Researches hotel options and destination information through web search. |
| Weather specialist | Retrieves current weather and forecast data through the custom weather MCP server. |
| Itinerary specialist | Turns the request and research results into a day-by-day travel plan. |
| Final response specialist | Produces the structured answer shown to the traveler. |
| PostgreSQL checkpointer | Stores LangGraph state associated with a conversation thread. |

The current graph is sequential rather than supervisor-routed: flight search runs first, followed by hotel research, weather lookup, itinerary generation, and final response composition.

## Tools and services

### LangGraph

LangGraph is the workflow engine. It owns the shared travel state, executes the specialist stages in order, and connects the workflow to PostgreSQL checkpointing.

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
- The workflow currently runs specialist stages in a fixed sequence rather than using supervisor routing.
- MCP tool availability depends on the hosted Tavily endpoint, `uvx` and the AviationStack MCP package, and the local custom weather server.
- Guardrail policy checks and human approval are not yet represented as graph nodes or interrupts.
- The included container file and dependency files should be kept aligned before container deployment.

The next evolution is to add input and output guardrail stages around the MCP-enabled graph, introduce a human approval checkpoint before any future booking or other consequential action, and expand the MCP tool set as the assistant grows.

## License

See [LICENSE](LICENSE).

