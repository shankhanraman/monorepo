import Keycloak from "keycloak-js";

export const keycloak = new Keycloak({
  url: "http://keycloak.lab.local:8080",
  realm: "lab",
  clientId: "frontend",
});
