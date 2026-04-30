"""Thin client for the Materials Project REST API.

This client intentionally uses direct HTTP requests so it works even when the
official ``mp_api`` package is not installed locally. It targets the current
Materials Project API at ``https://api.materialsproject.org``.
"""

from __future__ import annotations

import os
from urllib.parse import urljoin

import requests

DEFAULT_BASE_URL = "https://api.materialsproject.org"
DEFAULT_PAGE_SIZE = 100


class MaterialsProjectClient:
    """Minimal client for common Materials Project material queries."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("MP_API_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("MP_API_KEY", "")
        self.session = session or requests.Session()
        self.timeout = timeout

    def set_api_key(self, api_key: str) -> None:
        """Set the API key used for subsequent requests."""
        self.api_key = api_key.strip()

    def verify_api_key(self) -> dict:
        """Validate credentials with a small summary query."""
        result = self.get_material_summary("mp-149", fields=["material_id", "formula_pretty"])
        if not result:
            raise RuntimeError("API key verification returned no data.")
        return result

    def get_material_summary(
        self, material_id: str, fields: list[str] | None = None
    ) -> dict:
        """Fetch summary data for a single MP material ID."""
        response = self._fetch_documents(
            "materials/summary",
            self._with_fields(
                {"material_ids": material_id},
                fields=fields,
            ),
            limit=1,
        )
        docs = response.get("data", [])
        return docs[0] if docs else {}

    def search_materials(
        self,
        *,
        material_ids: list[str] | None = None,
        formula: str | list[str] | None = None,
        chemsys: str | list[str] | None = None,
        elements: list[str] | None = None,
        exclude_elements: list[str] | None = None,
        band_gap: tuple[float | None, float | None] | None = None,
        energy_above_hull: tuple[float | None, float | None] | None = None,
        is_stable: bool | None = None,
        is_metal: bool | None = None,
        num_elements: tuple[int | None, int | None] | None = None,
        num_sites: tuple[int | None, int | None] | None = None,
        spacegroup_symbol: str | list[str] | None = None,
        fields: list[str] | None = None,
        limit: int = 10,
        sort_fields: str | None = None,
    ) -> dict:
        """Search summary documents with common filter fields."""
        params: dict[str, object] = {}

        if material_ids:
            params["material_ids"] = self._csv(material_ids)
        if formula:
            params["formula"] = self._csv(formula)
        if chemsys:
            params["chemsys"] = self._csv(chemsys)
        if elements:
            params["elements"] = self._csv(elements)
        if exclude_elements:
            params["exclude_elements"] = self._csv(exclude_elements)
        if band_gap:
            if band_gap[0] is not None:
                params["band_gap_min"] = band_gap[0]
            if band_gap[1] is not None:
                params["band_gap_max"] = band_gap[1]
        if energy_above_hull:
            if energy_above_hull[0] is not None:
                params["energy_above_hull_min"] = energy_above_hull[0]
            if energy_above_hull[1] is not None:
                params["energy_above_hull_max"] = energy_above_hull[1]
        if is_stable is not None:
            params["is_stable"] = is_stable
        if is_metal is not None:
            params["is_metal"] = is_metal
        if num_elements:
            if num_elements[0] is not None:
                params["nelements_min"] = num_elements[0]
            if num_elements[1] is not None:
                params["nelements_max"] = num_elements[1]
        if num_sites:
            if num_sites[0] is not None:
                params["nsites_min"] = num_sites[0]
            if num_sites[1] is not None:
                params["nsites_max"] = num_sites[1]
        if spacegroup_symbol:
            params["spacegroup_symbol"] = self._csv(spacegroup_symbol)
        if sort_fields:
            params["_sort_fields"] = sort_fields

        return self._fetch_documents(
            "materials/summary",
            self._with_fields(params, fields=fields),
            limit=limit,
        )

    def get_structure(self, material_id: str, final: bool = True) -> dict | list[dict]:
        """Fetch final or initial structures for a material."""
        field = "structure" if final else "initial_structures"
        response = self._fetch_documents(
            "materials/core",
            self._with_fields({"material_ids": material_id}, fields=[field]),
            limit=1,
        )
        docs = response.get("data", [])
        if not docs:
            return {}
        return docs[0].get(field, {})

    def get_endpoint_data(
        self,
        endpoint: str,
        material_id: str,
        fields: list[str] | None = None,
        limit: int = 10,
    ) -> dict:
        """Fetch data for a specific materials endpoint by material ID."""
        endpoint = self._normalize_endpoint(endpoint)
        return self._fetch_documents(
            f"materials/{endpoint}",
            self._with_fields({"material_ids": material_id}, fields=fields),
            limit=limit,
        )

    def _fetch_documents(self, path: str, params: dict[str, object], limit: int) -> dict:
        """Fetch one or more pages from a Materials Project endpoint."""
        if limit < 1:
            raise ValueError("limit must be at least 1")

        collected: list[dict] = []
        meta: dict = {}
        skip = 0
        page_size = min(limit, DEFAULT_PAGE_SIZE)

        while len(collected) < limit:
            page_params = dict(params)
            page_params["_limit"] = min(page_size, limit - len(collected))
            if skip:
                page_params["_skip"] = skip

            payload = self._request(path, page_params)
            docs = payload.get("data", [])
            if not isinstance(docs, list):
                docs = [docs]

            if not meta:
                meta = payload.get("meta", {})

            collected.extend(docs)

            total_doc = meta.get("total_doc", len(collected))
            if not docs or len(collected) >= total_doc:
                break

            skip += len(docs)

        return {"data": collected[:limit], "meta": meta}

    def _request(self, path: str, params: dict[str, object]) -> dict:
        """Issue a GET request and return parsed JSON."""
        if not self.api_key:
            raise RuntimeError("Materials Project API key not set. Call authenticate_materials_project() first.")

        url = urljoin(f"{self.base_url}/", path.strip("/") + "/")
        response = self.session.get(
            url,
            headers={
                "Accept": "application/json",
                "x-api-key": self.api_key,
            },
            params=params,
            timeout=self.timeout,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Invalid response from Materials Project API: {response.text}") from exc

        if not response.ok:
            detail = payload.get("detail", response.text)
            raise RuntimeError(
                f"Materials Project API request failed ({response.status_code}) for {response.url}: {detail}"
            )

        return payload

    @staticmethod
    def _csv(value: str | list[str]) -> str:
        if isinstance(value, str):
            return value
        return ",".join(item for item in value if item)

    @staticmethod
    def _with_fields(
        params: dict[str, object],
        *,
        fields: list[str] | None,
    ) -> dict[str, object]:
        query = dict(params)
        if fields:
            query["_fields"] = ",".join(fields)
        else:
            query["_all_fields"] = True
        return query

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        cleaned = endpoint.strip().strip("/")
        if not cleaned:
            raise ValueError("endpoint must not be empty")
        if cleaned.startswith("materials/"):
            cleaned = cleaned[len("materials/") :]
        if ".." in cleaned:
            raise ValueError("endpoint must not contain '..'")
        return cleaned
