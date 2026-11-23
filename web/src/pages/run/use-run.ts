// The run detail, shared by the Run page and the request pages. It is not refreshed in the
// background: the version on the page is the version the person acts on (research R-08).
import { useQuery } from "@tanstack/react-query";

import { api, call } from "../../api/client";
import { keys } from "../../api/queries";

export function useRun(runId: string) {
  return useQuery({
    queryKey: keys.run(runId),
    queryFn: () => call(api.GET("/runs/{run_id}", { params: { path: { run_id: runId } } })),
    enabled: runId !== "",
    staleTime: Infinity,
  });
}
