import { describe, expect, it } from "vitest";

import enPack from "../messages/packs/en-US";
import esPack from "../messages/packs/es-ES";

describe("Spanish UI locale asset", () => {
  it("covers every current English source key without duplicates", () => {
    const enKeys = Object.keys(enPack).sort();
    const esKeys = Object.keys(esPack).sort();

    expect(new Set(esKeys).size).toBe(esKeys.length);
    expect(esKeys).toEqual(enKeys);
  });

  it("translates representative UI chrome while preserving placeholders", () => {
    expect(esPack["catalog.catalogDrawer.close"]).toBe("Cerrar catálogo");
    expect(esPack["personaLanguage.followUi"]).toBe("Seguir la interfaz de usuario");
    expect(esPack["catalog.personaCatalog.ready"]).toContain("{count}");
    expect(esPack["catalog.personaCatalog.ready"]).not.toBe(
      enPack["catalog.personaCatalog.ready"],
    );
  });
});
