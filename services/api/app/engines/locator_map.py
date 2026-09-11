"""Declarative locator registry for the generated POM pages.

The executor can only heal a locator it can name, so codegen ships this map
alongside the files: for each page-object property, the exact source expression
it emitted and a *probe* the runner can execute against the live DOM.

`probe` is deliberately structured (role/name, testid, placeholder, css) rather
than a raw Playwright expression — the runner must be able to evaluate it
without ever eval-ing generated code.

Drift guard: `verify()` asserts every expression here actually appears in the
generated file. If a template is edited without updating this table, the test
suite fails instead of the heal loop silently targeting the wrong thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Locator:
    file: str  # path relative to the bundle root
    prop: str  # page-object property name
    element: str  # human description, used to match a failed test to an element
    expr: str  # exact TS expression as emitted
    probe: dict = field(default_factory=dict)  # runner-executable existence check


def _l(file: str, prop: str, element: str, expr: str, **probe: str) -> Locator:
    return Locator(file=file, prop=prop, element=element, expr=expr, probe=dict(probe))


SAUCEDEMO = [
    _l("tests/pages/login.page.ts", "usernameInput", "Username input",
       'page.getByPlaceholder("Username")', placeholder="Username"),
    _l("tests/pages/login.page.ts", "passwordInput", "Password input",
       'page.getByPlaceholder("Password")', placeholder="Password"),
    _l("tests/pages/login.page.ts", "loginButton", "Login button",
       'page.getByRole("button", { name: "Login" })', role="button", name="Login"),
    _l("tests/pages/login.page.ts", "errorMessage", "Login error message",
       'page.locator("[data-test=\\"error\\"]")', css='[data-test="error"]'),
    _l("tests/pages/inventory.page.ts", "title", "Inventory page title",
       'page.locator(".title")', css=".title"),
    _l("tests/pages/inventory.page.ts", "cartBadge", "Cart item count badge",
       'page.locator(".shopping_cart_badge")', css=".shopping_cart_badge"),
    _l("tests/pages/inventory.page.ts", "sortSelect", "Product sort dropdown",
       'page.locator("[data-test=\\"product-sort-container\\"]")',
       css='[data-test="product-sort-container"]'),
    _l("tests/pages/inventory.page.ts", "menuButton", "Open menu button",
       'page.getByRole("button", { name: "Open Menu" })', role="button", name="Open Menu"),
    _l("tests/pages/inventory.page.ts", "logoutLink", "Logout link",
       'page.getByRole("link", { name: "Logout" })', role="link", name="Logout"),
    _l("tests/pages/inventory.page.ts", "items", "Inventory items grid",
       'page.locator(".inventory_item")', css=".inventory_item"),
]

GENERIC = [
    _l("{page}", "heading", "Primary page heading",
       'page.getByRole("heading").first()', role="heading"),
    _l("{page}", "primaryAction", "Primary action button",
       'page.getByRole("button").first()', role="button"),
]


def for_kit(kit: str, page_file: str = "") -> list[Locator]:
    """Locator set for a template kit, with the generic placeholder resolved."""
    if kit == "saucedemo":
        return SAUCEDEMO
    return [
        Locator(
            file=page_file or loc.file,
            prop=loc.prop,
            element=loc.element,
            expr=loc.expr,
            probe=loc.probe,
        )
        for loc in GENERIC
    ]


def verify(locators: list[Locator], bundle: dict[str, str]) -> list[str]:
    """Return drift errors: locators whose expression is absent from the file.

    Called from tests. An empty list means the registry still describes the
    generated code, which is what the heal loop depends on.
    """
    errors: list[str] = []
    for loc in locators:
        source = bundle.get(loc.file)
        if source is None:
            errors.append(f"{loc.file}: file not in bundle")
            continue
        if loc.expr not in source:
            errors.append(f"{loc.file}:{loc.prop}: expression not found in generated source")
    return errors
