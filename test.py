from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights


# Test Tavily search
# res = tavily_search("Best hotels in India")
# print(res)


# Test Flight Search
res = search_flights("Plan a 7 days Nepal trip from odisha")
print(res)