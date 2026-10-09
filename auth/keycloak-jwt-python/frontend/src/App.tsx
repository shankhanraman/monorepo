import { useState } from "react";
import "./App.css";
import { keycloak } from "./auth/keycloak";
import SignInMenu from "./auth/SignInMenu";
import Me from "./me/Me";
import Profiles from "./profiles/Profiles";
import Users from "./users/Users";

export default function App() {
  // Login/logout are full-page redirects, so this can't change while the page is open.
  const signedIn = !!keycloak.authenticated;
  // Bumped on user changes so Profiles reloads (owner names, delete cascades).
  const [usersVersion, setUsersVersion] = useState(0);

  return (
    <main className="app">
      <header className="app-header">
        <h1>Keycloak JWT Lab</h1>
        <SignInMenu />
      </header>
      {signedIn ? <Me /> : <p className="muted">Browsing as guest. Sign in to add, edit or delete.</p>}
      <Users canEdit={signedIn} onChange={() => setUsersVersion((v) => v + 1)} />
      <Profiles canEdit={signedIn} version={usersVersion} />
    </main>
  );
}
