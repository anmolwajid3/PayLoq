import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import * as api from "./api";
import type { Lang } from "./i18n";

type AuthState = {
  token: string | null;
  username: string | null;
  lang: Lang;
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  setLang: (lang: Lang) => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("payloq_token"));
  const [username, setUsername] = useState<string | null>(
    () => localStorage.getItem("payloq_user"),
  );
  const [lang, setLangState] = useState<Lang>(
    () => (localStorage.getItem("payloq_lang") as Lang) || "fi",
  );
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!token) {
        if (!cancelled) setReady(true);
        return;
      }
      try {
        const u = await api.me();
        if (!cancelled) {
          setUsername(u.username);
          localStorage.setItem("payloq_user", u.username);
        }
      } catch {
        localStorage.removeItem("payloq_token");
        localStorage.removeItem("payloq_user");
        if (!cancelled) {
          setToken(null);
          setUsername(null);
        }
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const login = useCallback(async (user: string, password: string) => {
    const res = await api.login(user, password);
    localStorage.setItem("payloq_token", res.access_token);
    localStorage.setItem("payloq_user", res.username);
    setToken(res.access_token);
    setUsername(res.username);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("payloq_token");
    localStorage.removeItem("payloq_user");
    setToken(null);
    setUsername(null);
  }, []);

  const setLang = useCallback((l: Lang) => {
    localStorage.setItem("payloq_lang", l);
    setLangState(l);
  }, []);

  const value = useMemo(
    () => ({ token, username, lang, ready, login, logout, setLang }),
    [token, username, lang, ready, login, logout, setLang],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
