export async function direct(): Promise<Response> {
  return fetch("/api/inbox");
}
