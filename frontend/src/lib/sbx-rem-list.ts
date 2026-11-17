import createClient from "openapi-fetch";
import type { components, paths } from "@/lib/api/generated/sbx-rem-list";

export type Reminder = components["schemas"]["Reminder"];
export type ReminderPriority = Reminder["priority"];

type ListResult =
  | { status: 200; reminders: Reminder[] }
  | { status: 401 }
  | { status: "error" };

const api = createClient<paths>({ baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "" });

export async function listReminders(
  query: string,
  priority?: ReminderPriority,
): Promise<ListResult> {
  const token = window.sessionStorage.getItem("sbx-session-token");
  if (!token) {
    return { status: 401 };
  }

  const { data, response } = await api.GET("/api/reminders", {
    params: {
      query: {
        ...(query.trim() ? { q: query.trim() } : {}),
        ...(priority ? { priority } : {}),
      },
    },
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (response.status === 401) {
    window.sessionStorage.removeItem("sbx-session-token");
    return { status: 401 };
  }
  if (response.status !== 200 || !data) {
    return { status: "error" };
  }
  return { status: 200, reminders: data };
}
