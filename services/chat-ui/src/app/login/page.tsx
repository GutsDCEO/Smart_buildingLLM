"use client";

import { useState, useEffect, useRef, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiLogin, apiRegister, getStoredUser, validateSession } from "@/lib/auth";

// ── Mode type ─────────────────────────────────────────────────────
type AuthMode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const checkedRef = useRef(false);

  // Redirect if already authenticated — VERIFY with server first
  useEffect(() => {
    if (checkedRef.current) return;
    checkedRef.current = true;

    const cached = getStoredUser();
    if (!cached) return; // No local data — stay on login

    // Local data exists — ask the server if the session is still valid
    validateSession().then((freshUser) => {
      if (freshUser) {
        // Session is genuinely valid — redirect to home
        router.replace("/");
      }
      // If null → session is dead, clearAuth() already ran.
      // Stay on login page — user needs to log in again.
    });
  }, [router]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      let result;
      if (mode === "login") {
        result = await apiLogin(username.trim(), password);
      } else {
        // Register then auto-login
        const regResult = await apiRegister(username.trim(), email.trim(), password);
        if (regResult.error) {
          setError(regResult.error);
          return;
        }
        result = await apiLogin(username.trim(), password);
      }

      if (result.error) {
        setError(result.error);
      } else {
        router.replace("/");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const toggleMode = () => {
    setMode((m) => (m === "login" ? "register" : "login"));
    setError(null);
    setUsername("");
    setEmail("");
    setPassword("");
  };

  return (
    <div className="login-page">
      {/* Animated background particles */}
      <div className="login-bg">
        <div className="login-bg-orb login-bg-orb--1" />
        <div className="login-bg-orb login-bg-orb--2" />
        <div className="login-bg-orb login-bg-orb--3" />
      </div>

      {/* Card */}
      <div className="login-card">
        {/* Header */}
        <div className="login-header">
          <div className="login-logo">🏗️</div>
          <h1 className="login-title">Smart Building AI</h1>
          <p className="login-subtitle">
            {mode === "login" ? "Sign in to your account" : "Create your account"}
          </p>
        </div>

        {/* Form */}
        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <div className="login-field">
            <label htmlFor="login-username" className="login-label">
              Username
            </label>
            <input
              id="login-username"
              type="text"
              className="login-input"
              placeholder="Enter your username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              autoComplete="username"
              minLength={3}
              maxLength={50}
            />
          </div>

          {/* Email only shown on register */}
          {mode === "register" && (
            <div className="login-field" style={{ animation: "fadeSlideIn 0.2s ease" }}>
              <label htmlFor="login-email" className="login-label">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                className="login-input"
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>
          )}

          <div className="login-field">
            <label htmlFor="login-password" className="login-label">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              className="login-input"
              placeholder={mode === "register" ? "Minimum 8 characters" : "Enter your password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={8}
            />
          </div>

          {/* Error message */}
          {error && (
            <div className="login-error" role="alert">
              <span>⚠️</span>
              <span>{error}</span>
            </div>
          )}

          <button
            id="login-submit-btn"
            type="submit"
            className="login-btn"
            disabled={isLoading}
          >
            {isLoading ? (
              <span className="login-spinner" />
            ) : mode === "login" ? (
              "Sign In"
            ) : (
              "Create Account"
            )}
          </button>
        </form>

        {/* Mode toggle */}
        <div className="login-footer">
          <span className="login-footer-text">
            {mode === "login" ? "Don't have an account?" : "Already have an account?"}
          </span>
          <button
            id="login-mode-toggle"
            type="button"
            className="login-toggle-btn"
            onClick={toggleMode}
          >
            {mode === "login" ? "Create one" : "Sign in"}
          </button>
        </div>

        {/* First-user hint */}
        {mode === "register" && (
          <p className="login-hint">
            💡 The first registered user becomes the <strong>Admin</strong>.
          </p>
        )}
      </div>
    </div>
  );
}
