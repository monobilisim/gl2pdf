def _create_key(client, admin_headers):
    response = client.post("/admin/keys", headers=admin_headers, json={"name": "ci"})
    assert response.status_code == 201
    body = response.json()
    assert body["raw_key"]
    return body["id"], body["raw_key"]


def _convert(client, key, payload):
    return client.post("/convert", headers={"X-API-Key": key}, json=payload)


def test_probes(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_admin_key_lifecycle_and_auth(client, admin_headers, sast_payload):
    assert client.get("/admin/keys").status_code == 401

    key_id, raw_key = _create_key(client, admin_headers)
    listed = client.get("/admin/keys", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == key_id

    assert client.patch(f"/admin/keys/{key_id}/deactivate", headers=admin_headers).status_code == 200
    assert _convert(client, raw_key, sast_payload).status_code == 403

    assert client.patch(f"/admin/keys/{key_id}/activate", headers=admin_headers).status_code == 200
    assert _convert(client, raw_key, sast_payload).status_code == 200

    assert client.delete(f"/admin/keys/{key_id}", headers=admin_headers).status_code == 204
    assert _convert(client, raw_key, sast_payload).status_code == 403


def test_convert_sast_pdf(client, admin_headers, sast_payload):
    _, raw_key = _create_key(client, admin_headers)
    response = _convert(client, raw_key, sast_payload)
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert response.headers["X-Report-Type"] == "sast"


def test_convert_code_quality_pdf(client, admin_headers, cq_payload):
    _, raw_key = _create_key(client, admin_headers)
    response = _convert(client, raw_key, cq_payload)
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert response.headers["X-Report-Type"] == "codequality"


def test_convert_rejects_bad_requests(client, admin_headers):
    _, raw_key = _create_key(client, admin_headers)
    assert client.post("/convert", json={"vulnerabilities": []}).status_code == 401
    assert client.post("/convert", headers={"X-API-Key": "garbage"}, json={"vulnerabilities": []}).status_code == 403
    assert client.post("/convert", headers={"X-API-Key": raw_key}, content=b"").status_code == 400
    assert client.post("/convert", headers={"X-API-Key": raw_key}, content=b"{").status_code == 400
    assert client.post("/convert", headers={"X-API-Key": raw_key}, json={"foo": "bar"}).status_code == 400
