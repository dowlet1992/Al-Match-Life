(() => {
    "use strict";
    const form = document.getElementById("registerForm");
    if (!form) return;

    const byId = (id) => document.getElementById(id);
    const contactType = byId("contact_type");
    const emailInput = byId("email");
    const phoneInput = byId("phone");
    const countryCodeInput = byId("country_code");
    const phoneLocalInput = byId("phone_local");
    const emailField = byId("emailField");
    const phoneField = byId("phoneField");
    const password = byId("password");
    const passwordConfirm = byId("password_confirm");
    const passwordError = byId("passwordError");

    function regionFlag(region) {
        return [...region].map((letter) =>
            String.fromCodePoint(127397 + letter.charCodeAt(0))
        ).join("");
    }

    function localizeCountryCodes() {
        if (!countryCodeInput || typeof Intl.DisplayNames !== "function") return;
        const locale = document.documentElement.lang || "en";
        const regionNames = new Intl.DisplayNames([locale], {type: "region"});
        countryCodeInput.querySelectorAll("option[data-region]").forEach((option) => {
            const region = option.dataset.region;
            const name = regionNames.of(region) || region;
            option.textContent = `${regionFlag(region)} ${name} ${option.value}`;
        });
    }

    function updateContactMethod() {
        const useEmail = contactType.value === "email";
        emailInput.required = useEmail;
        emailInput.disabled = !useEmail;
        phoneLocalInput.required = !useEmail;
        phoneLocalInput.disabled = useEmail;
        countryCodeInput.disabled = useEmail;
        emailField.hidden = !useEmail;
        phoneField.hidden = useEmail;
    }

    contactType.addEventListener("change", updateContactMethod);
    localizeCountryCodes();
    updateContactMethod();

    document.querySelectorAll(".toggle-password").forEach((button) => {
        button.addEventListener("click", () => {
            const input = byId(button.dataset.target);
            if (!input) return;
            const show = input.type === "password";
            input.type = show ? "text" : "password";
            button.textContent = show ? button.dataset.hideLabel : button.dataset.showLabel;
            button.setAttribute("aria-pressed", String(show));
        });
    });

    form.addEventListener("submit", (event) => {
        const firstName = byId("first_name").value.trim();
        const lastName = byId("last_name").value.trim();
        byId("full_name").value = `${firstName} ${lastName}`.trim();
        const cleanLocalPhone = phoneLocalInput.value.replace(/\D/g, "").replace(/^0+/, "");
        phoneInput.value = cleanLocalPhone ? `${countryCodeInput.value}${cleanLocalPhone}` : "";

        const passwordsMatch = password.value === passwordConfirm.value;
        passwordError.classList.toggle("is-visible", !passwordsMatch);
        passwordConfirm.setAttribute("aria-invalid", String(!passwordsMatch));
        if (!passwordsMatch) {
            event.preventDefault();
            passwordConfirm.focus();
        }
    });
})();
