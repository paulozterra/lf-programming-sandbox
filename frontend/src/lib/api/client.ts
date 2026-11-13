import createClient from "openapi-fetch";

/** All API calls must use openapi-fetch bound to generated OpenAPI path types. */
export function clientFor<Paths extends Record<string, object>>(baseUrl: string) {
  return createClient<Paths>({ baseUrl });
}
