import createClient from "openapi-fetch";
import type { components, paths } from "@/lib/api/generated/sbx-b2b-login";

export const LOGIN_ROUTE = "/sbx-b2b-login";
export const REMINDERS_ROUTE = "/sbx-rem-list";
export const SESSION_KEY = "sbx-session-token";
const api = createClient<paths>({ baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "" });

export const tokens = {
  navy_core: "#0F172A",
  navy_muted: "#334155",
  warm_surface: "#FDFCFA",
  card_surface: "#FFFFFF",
  border_soft: "#E2E8F0",
  error_bg: "#FEE2E2",
  error_text: "#991B1B",
  green_action: "#109044",
  green_action_hover: "#0d7336",
  blue_brand_accent: "#2563EB",
  space_4: "4px",
  space_8: "8px",
  space_12: "12px",
  space_16: "16px",
  space_24: "24px",
  space_32: "32px",
  space_48: "48px",
  space_64: "64px",
  radius_12: "12px",
  radius_16: "16px",
  radius_24: "24px",
  text_section_h2: { fontSize: "32px", lineHeight: "40px", fontWeight: 700 },
  text_body: { fontSize: "16px", lineHeight: "24px" },
  text_body_small: { fontSize: "14px", lineHeight: "20px" },
  text_button: { fontSize: "14px", lineHeight: "20px", fontWeight: 700 },
  font_family_base: "Inter, sans-serif",
} as const;

export const errorCatalog = {
  "SBX-B2B-E-CREDENTIALS": {
    title: "No pudimos iniciar sesión",
    message: "No pudimos validar tus datos de acceso. Revisa la información e inténtalo nuevamente.",
    suggestedAction: "Verifica tu correo y contraseña. Si no recuerdas tu contraseña, utiliza la opción de recuperación.",
    actionLabel: "Revisar datos",
  },
  "SBX-B2B-E-RATE": {
    title: "Demasiadas solicitudes",
    message: "Se alcanzó temporalmente el límite de operaciones.",
    suggestedAction: "Espere unos minutos antes de volver a intentar.",
    actionLabel: "Reintentar después",
  },
  "SBX-B2B-E-NETWORK": {
    title: "Conexión interrumpida",
    message: "Se perdió la conexión durante la operación.",
    suggestedAction: "Verifique su conexión. La aplicación intentará recuperar el estado.",
    actionLabel: "Reintentar",
  },
  "SBX-B2B-E-UNEXPECTED": {
    title: "No pudimos completar la operación",
    message: "Ocurrió un error inesperado.",
    suggestedAction: "Use el código de referencia para solicitar soporte.",
    actionLabel: "Contactar soporte",
  },
} as const;
export type ErrorCode = keyof typeof errorCatalog;
type Failure = components["schemas"]["LoginFailure"];
type Success = components["schemas"]["LoginSuccess"];
export type Result = { ok: true; success: Success } | { ok: false; code: ErrorCode; correlationId?: string };

function known(code: unknown): code is ErrorCode {
  return typeof code === "string" && Object.prototype.hasOwnProperty.call(errorCatalog, code);
}
export async function authenticate(email: string, password: string): Promise<Result> {
  try {
    const { response, data, error } = await api.POST("/api/auth/login", { body: { email, password } });
    if (response.status === 200 && data?.outcome === "AUTHENTICATED" && data.token) {
      return { ok: true, success: data };
    }
    const failure = error as Failure | undefined;
    const fallback: ErrorCode = response.status === 401
      ? "SBX-B2B-E-CREDENTIALS"
      : response.status === 429
        ? "SBX-B2B-E-RATE"
        : response.status === 503
          ? "SBX-B2B-E-NETWORK"
          : "SBX-B2B-E-UNEXPECTED";
    return { ok: false, code: known(failure?.error_code) ? failure.error_code : fallback, correlationId: failure?.correlation_id };
  } catch {
    return { ok: false, code: "SBX-B2B-E-NETWORK" };
  }
}
export function returnPath(search: string): string {
  const next = new URLSearchParams(search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") && !next.includes("\\") && !/[\r\n]/.test(next)
    ? next : REMINDERS_ROUTE;
}
