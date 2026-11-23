import createClient from "openapi-fetch";

export const client = createClient({ baseUrl: "/api" });
