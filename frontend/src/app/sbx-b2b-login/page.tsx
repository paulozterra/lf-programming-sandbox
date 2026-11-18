"use client";

import { useRef, useState, type CSSProperties, type FormEvent } from "react";
import { authenticate, errorCatalog, returnPath, SESSION_KEY, tokens, type ErrorCode } from "@/lib/sbx-b2b-login";

const t = tokens;
const emailMessage = "Ingresa un correo electrónico válido. Ejemplo: usuario@empresa.com";
const passwordMessage = "Ingresa tu contraseña.";

function validEmail(emailValue: string): boolean {
  const email = emailValue.trim();
  if (!email || email.length > 254 || /\s/.test(email) || email.includes("..")) return false;
  const parts = email.split("@");
  if (parts.length !== 2 || !parts[0] || parts[0].startsWith(".") || parts[0].endsWith(".")) return false;
  const labels = parts[1].split(".");
  return labels.length >= 2 && labels.every((label) => Boolean(label) && !label.startsWith("-") && !label.endsWith("-"));
}

type IconName = "Mail" | "LockKeyhole" | "Eye" | "EyeOff";
function Icon({ name }: { name: IconName }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {name === "Mail" && <><rect x="2" y="4" width="20" height="16" rx="2" /><path d="m22 7-10 6L2 7" /></>}
      {name === "LockKeyhole" && <><rect x="4" y="10" width="16" height="12" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3M12 15v2" /></>}
      {name === "Eye" && <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>}
      {name === "EyeOff" && <><path d="m3 3 18 18M10.6 5.1A11 11 0 0 1 12 5c6 0 10 7 10 7a14 14 0 0 1-3 3.7M6.3 6.3C3.6 8.2 2 12 2 12s4 7 10 7c1.2 0 2.4-.3 3.5-.8" /></>}
    </svg>
  );
}
const inputStyle: CSSProperties = {
  boxSizing: "border-box", width: "100%", background: t.card_surface, color: t.navy_core,
  border: `1px solid ${t.border_soft}`, borderRadius: t.radius_12,
  padding: `${t.space_16} ${t.space_48}`, font: "inherit",
};
const linkStyle: CSSProperties = {
  color: t.blue_brand_accent, textDecoration: "underline", ...t.text_body_small,
};

export default function SbxB2bLoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [emailError, setEmailError] = useState(false);
  const [passwordError, setPasswordError] = useState(false);
  const [error, setError] = useState<{ code: ErrorCode; correlationId?: string } | null>(null);
  const inFlight = useRef(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const badEmail = !validEmail(email);
    const badPassword = password.length === 0;
    setEmailError(badEmail);
    setPasswordError(badPassword);
    setError(null);
    if (badEmail || badPassword) return;
    inFlight.current = true;
    setPending(true);
    try {
      const result = await authenticate(email.trim(), password);
      if (result.ok) {
        window.sessionStorage.setItem(SESSION_KEY, result.success.token);
        window.location.assign(returnPath(window.location.search));
      } else {
        setError({ code: result.code, correlationId: result.correlationId });
      }
    } finally {
      setPending(false);
      inFlight.current = false;
    }
  }

  const currentError = error ? errorCatalog[error.code] : null;
  return (
    <main style={{ minHeight: "100dvh", display: "flex", flexDirection: "column", boxSizing: "border-box",
      background: t.warm_surface, color: t.navy_core, fontFamily: t.font_family_base, padding: t.space_24 }}>
      <style>{`
        .sbx-b2b-shell { container-type: inline-size; flex: 1; display: grid; place-items: center; }
        .sbx-b2b-form { width: 100%; max-width: calc(${t.space_64} * 8); }
        .sbx-b2b-focus:focus-visible { outline: 3px solid ${t.blue_brand_accent}; outline-offset: ${t.space_4}; }
        .sbx-b2b-submit:hover:not(:disabled) { background: ${t.green_action_hover} !important; }
        .sbx-b2b-submit:disabled { opacity: .7; cursor: wait; }
        @container (max-width: 480px) { .sbx-b2b-form { max-width: 100%; } }
        @media (forced-colors: active) {
          .sbx-b2b-focus:focus-visible { outline-color: Highlight; }
          .sbx-b2b-submit, .sbx-b2b-field { border: 1px solid ButtonText !important; }
        }
        @media (prefers-reduced-motion: reduce) {
          .sbx-b2b-form * { transition: none !important; animation: none !important; }
        }
      `}</style>
      <header style={{ display: "flex", justifyContent: "flex-end", paddingBottom: t.space_24 }}>
        <strong style={{ textAlign: "right" }}>Backoffice Empresa</strong>
      </header>
      <section className="sbx-b2b-shell" aria-label="Iniciar sesión">
        <form className="sbx-b2b-form" onSubmit={(event) => void submit(event)} noValidate>
          <h1 style={{ ...t.text_section_h2, margin: `0 0 ${t.space_32}` }}>Iniciar sesión</h1>
          <div style={{ marginBottom: t.space_24 }}>
            <label htmlFor="sbx-email" style={{ display: "block", marginBottom: t.space_8, ...t.text_body_small }}>
              Correo electrónico
            </label>
            <div style={{ position: "relative" }}>
              <span aria-hidden="true" style={{ position: "absolute", left: t.space_16, top: t.space_16, color: t.navy_muted }}>
                <Icon name="Mail" />
              </span>
              <input className="sbx-b2b-field sbx-b2b-focus" id="sbx-email" type="email" name="email"
                autoComplete="username" placeholder="ejemplo@empresa.com" maxLength={254} required
                value={email} aria-invalid={emailError} aria-describedby={emailError ? "sbx-email-error" : undefined}
                onChange={(event) => { setEmail(event.target.value); setEmailError(false); }} style={inputStyle} />
            </div>
            {emailError && <p role="alert" id="sbx-email-error" style={{ color: t.error_text, ...t.text_body_small }}>{emailMessage}</p>}
          </div>
          <div>
            <label htmlFor="sbx-password" style={{ display: "block", marginBottom: t.space_8, ...t.text_body_small }}>
              Contraseña
            </label>
            <div style={{ position: "relative" }}>
              <span aria-hidden="true" style={{ position: "absolute", top: t.space_16, left: t.space_16, color: t.navy_muted }}>
                <Icon name="LockKeyhole" />
              </span>
              <input className="sbx-b2b-field sbx-b2b-focus" id="sbx-password" name="password" required
                type={visible ? "text" : "password"} autoComplete="current-password"
                placeholder="Ingresa tu contraseña" value={password}
                aria-invalid={passwordError} aria-describedby={passwordError ? "sbx-password-error" : undefined}
                onChange={(event) => { setPassword(event.target.value); setPasswordError(false); }} style={inputStyle} />
              <button type="button" className="sbx-b2b-focus" aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
                aria-pressed={visible} onClick={() => setVisible((wasVisible) => !wasVisible)}
                style={{ position: "absolute", right: t.space_8, top: t.space_4, minHeight: t.space_48, minWidth: t.space_48,
                  background: "transparent", border: 0, color: t.navy_muted, cursor: "pointer" }}>
                <Icon name={visible ? "EyeOff" : "Eye"} />
              </button>
            </div>
            {passwordError && <p role="alert" id="sbx-password-error" style={{ color: t.error_text, ...t.text_body_small }}>{passwordMessage}</p>}
            <div style={{ marginTop: t.space_12, textAlign: "right" }}>
              <a className="sbx-b2b-focus" href="#" style={linkStyle} onClick={(event) => event.preventDefault()}>
                ¿Olvidaste tu contraseña?
              </a>
            </div>
          </div>
          {currentError && <div role="alert" style={{ background: t.error_bg, color: t.error_text,
            borderRadius: t.radius_12, padding: t.space_16, marginTop: t.space_24 }}>
            <strong>{currentError.title}</strong>
            <p>{currentError.message}</p>
            <p>{currentError.suggestedAction}</p>
            <p>{currentError.actionLabel}{error?.correlationId ? ` · ${error.correlationId}` : ""}</p>
          </div>}
          <button className="sbx-b2b-submit sbx-b2b-focus" type="submit" disabled={pending} aria-busy={pending}
            style={{ display: "block", width: "100%", marginTop: t.space_24, padding: t.space_16,
              border: 0, borderRadius: t.radius_12, background: t.green_action,
              color: t.card_surface, cursor: "pointer", ...t.text_button }}>
            Acceder
          </button>
          <span role="status" aria-live="polite" style={{ ...t.text_body_small, color: t.navy_muted }}>
            {pending ? "Acceder" : ""}
          </span>
        </form>
      </section>
      <footer style={{ display: "flex", justifyContent: "center", flexWrap: "wrap", gap: t.space_24, paddingTop: t.space_32 }}>
        {["Términos y condiciones", "Política de privacidad", "Contáctanos"].map((label) => (
          <a className="sbx-b2b-focus" key={label} href="#" style={linkStyle}
            onClick={(event) => event.preventDefault()}>{label}</a>
        ))}
      </footer>
    </main>
  );
}
