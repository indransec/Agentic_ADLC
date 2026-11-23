// The one network module: errors in the platform's shape, the CSRF header on changes only, and
// "unavailable" when the platform cannot be reached (N-06).
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiUrl, json, refusal } from "../test/msw-handlers";
import { server } from "../test/msw-server";
import { api, call, CSRF_HEADER, onSessionEnded, setCsrfToken } from "./client";
import { ApiError } from "./errors";

afterEach(() => {
  setCsrfToken(null);
  onSessionEnded(null);
});

describe("call", () => {
  it("returns the data", async () => {
    server.use(http.get(apiUrl("/inbox"), () => json([])));
    await expect(call(api.GET("/inbox"))).resolves.toEqual([]);
  });

  it.each([
    [401, "not_signed_in"],
    [403, "not_allowed"],
    [404, "not_found"],
    [409, "stale"],
    [409, "wrong_state"],
    [422, "invalid"],
    [502, "unavailable"],
  ])("maps %i %s", async (status, kind) => {
    server.use(http.get(apiUrl("/inbox"), () => refusal(status, kind, "the reason", "name")));
    const error = await call(api.GET("/inbox"), { quietSignedOut: true }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status, kind, detail: "the reason", field: "name" });
  });

  it("an answer outside the platform's shape is unknown", async () => {
    server.use(http.get(apiUrl("/inbox"), () => new HttpResponse("<html>", { status: 500 })));
    await expect(call(api.GET("/inbox"))).rejects.toMatchObject({ kind: "unknown", status: 500 });
  });

  it("a network failure is unavailable", async () => {
    server.use(http.get(apiUrl("/inbox"), () => HttpResponse.error()));
    await expect(call(api.GET("/inbox"))).rejects.toMatchObject({ kind: "unavailable" });
  });

  it("a 401 ends the session unless the call expects it", async () => {
    const ended = vi.fn();
    onSessionEnded(ended);
    server.use(http.get(apiUrl("/inbox"), () => refusal(401, "not_signed_in", "expired")));
    await call(api.GET("/inbox"), { quietSignedOut: true }).catch(() => undefined);
    expect(ended).not.toHaveBeenCalled();
    await call(api.GET("/inbox")).catch(() => undefined);
    expect(ended).toHaveBeenCalledOnce();
  });
});

describe("CSRF header", () => {
  it("is sent on changes, never on reads", async () => {
    setCsrfToken("value-1");
    const seen: (string | null)[] = [];
    server.use(
      http.get(apiUrl("/inbox"), ({ request }) => {
        seen.push(request.headers.get(CSRF_HEADER));
        return json([]);
      }),
      http.post(apiUrl("/usecases"), ({ request }) => {
        seen.push(request.headers.get(CSRF_HEADER));
        return json({ usecase_id: "UC-0001" }, 201);
      }),
    );
    await call(api.GET("/inbox"));
    await call(api.POST("/usecases", { body: { name: "n", intake_text: "t" } }));
    expect(seen).toEqual([null, "value-1"]);
  });

  it("is absent when there is no session value", async () => {
    let seen: string | null = "unset";
    server.use(
      http.post(apiUrl("/usecases"), ({ request }) => {
        seen = request.headers.get(CSRF_HEADER);
        return json({ usecase_id: "UC-0001" }, 201);
      }),
    );
    await call(api.POST("/usecases", { body: { name: "n", intake_text: "t" } }));
    expect(seen).toBeNull();
  });
});
