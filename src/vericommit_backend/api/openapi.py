"""Keep generated documentation consistent with the approved HTTP 400 policy."""

from fastapi import FastAPI


def configure_openapi(application: FastAPI) -> None:
    generate_openapi = application.openapi

    def openapi() -> dict:
        schema = generate_openapi()
        # FastAPI otherwise adds its built-in 422 envelope despite our handler.
        responses = schema["paths"]["/api/v1/evaluations"]["post"]["responses"]
        responses.pop("422", None)
        return schema

    application.openapi = openapi
