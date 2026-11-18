"use client";

import { useEffect, useState } from "react";
import {
  listReminders,
  type Reminder,
  type ReminderPriority,
} from "@/lib/sbx-rem-list";

const LOGIN_PATH = "/sbx-b2b-login?next=/sbx-rem-list";

export default function SbxRemListPage() {
  const [query, setQuery] = useState("");
  const [priority, setPriority] = useState<ReminderPriority | "">("");
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    void listReminders(query, priority || undefined)
      .then((result) => {
        if (!active) return;
        if (result.status === 401) {
          window.location.assign(LOGIN_PATH);
          return;
        }
        if (result.status !== 200) {
          setReminders([]);
          setError(true);
          return;
        }
        setReminders(result.reminders);
        setError(false);
      })
      .catch(() => {
        if (!active) return;
        setReminders([]);
        setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [query, priority]);

  return (
    <main>
      <h1>Recordatorios</h1>
      <section aria-label="Filtros de recordatorios">
        <label htmlFor="reminder-search">Buscar</label>
        <input
          id="reminder-search"
          type="search"
          value={query}
          onChange={(event) => {
            setLoading(true);
            setQuery(event.target.value);
          }}
        />
        <label htmlFor="reminder-priority">Prioridad</label>
        <select
          id="reminder-priority"
          value={priority}
          onChange={(event) => {
            setLoading(true);
            setPriority(event.target.value as ReminderPriority | "");
          }}
        >
          <option value="">Todas</option>
          <option value="HIGH">Alta</option>
          <option value="MEDIUM">Media</option>
          <option value="LOW">Baja</option>
        </select>
      </section>
      {loading && <p role="status">Cargando recordatorios...</p>}
      {error && <p role="alert">SBX-E-GENERIC</p>}
      {!loading && !error && (
        <ul aria-label="Lista de recordatorios">
          {reminders.map((reminder) => (
            <li key={reminder.id}>
              <span>{reminder.text}</span>{" "}
              <time>{reminder.at}</time>{" "}
              <span>{reminder.priority}</span>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
