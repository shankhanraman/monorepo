import { useState } from "react";
import "./App.css";
import { session } from "./auth/session";
import SignInMenu from "./auth/SignInMenu";
import Me from "./me/Me";
import Profiles from "./profiles/Profiles";
import Users from "./users/Users";

export default function App() {
  // Login/logout are full-page navigations, so this can't change while the page is open.
  const signedIn = session.user !== null;
  // Bumped on user changes so Profiles reloads (owner names, delete cascades).
  const [usersVersion, setUsersVersion] = useState(0);

  return (
    <main className="app">
      <header className="app-header">
        <h1>OAuth 2.0 BFF Lab</h1>
        <SignInMenu />
      </header>
      {signedIn ? <Me /> : <p className="muted">Browsing as guest. Sign in to add, edit or delete.</p>}
      <Users canEdit={signedIn} onChange={() => setUsersVersion((v) => v + 1)} />
      <Profiles canEdit={signedIn} version={usersVersion} />
    </main>
  );
}
