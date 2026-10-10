import warnings

from sqlalchemy.exc import SAWarning

# SQLite has no exact decimal type (Postgres does); fine for these tests.
warnings.filterwarnings("ignore", category=SAWarning, message=".*Decimal objects natively.*")

ITEM = {"name": "Coffee", "description": "1 kg beans", "price": "12.50"}


def test_crud_lifecycle(client):
    # create
    r = client.post("/items/", json=ITEM)
    assert r.status_code == 201
    item = r.json()
    assert item["name"] == "Coffee" and item["price"] == "12.50" and item["id"] and item["created_at"]

    # read
    assert client.get(f"/items/{item['id']}").json()["description"] == "1 kg beans"
    assert [i["id"] for i in client.get("/items/").json()] == [item["id"]]

    # update (full replace: description left out → cleared)
    r = client.put(f"/items/{item['id']}", json={"name": "Tea", "price": 4})
    assert r.status_code == 200
    assert r.json() | {"created_at": None} == {"id": item["id"], "name": "Tea", "description": None,
                                               "price": "4.00", "created_at": None}

    # delete
    assert client.delete(f"/items/{item['id']}").status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_not_found(client):
    assert client.get("/items/999").status_code == 404
    assert client.put("/items/999", json=ITEM).status_code == 404
    assert client.delete("/items/999").status_code == 404


def test_validation(client):
    assert client.post("/items/", json={**ITEM, "name": ""}).status_code == 422
    assert client.post("/items/", json={**ITEM, "name": "x" * 101}).status_code == 422
    assert client.post("/items/", json={**ITEM, "price": "-1"}).status_code == 422
    assert client.post("/items/", json={**ITEM, "price": "1.234"}).status_code == 422  # max 2 decimals
    assert client.post("/items/", json={"name": "No price"}).status_code == 422
    assert client.get("/items/?limit=0").status_code == 422
    assert client.get("/items/?limit=101").status_code == 422


def test_paging_is_ordered_by_id(client):
    ids = [client.post("/items/", json={**ITEM, "name": f"item {n}"}).json()["id"] for n in range(5)]
    assert [i["id"] for i in client.get("/items/?limit=2").json()] == ids[:2]
    assert [i["id"] for i in client.get("/items/?limit=2&offset=2").json()] == ids[2:4]
    assert client.get("/items/?offset=10").json() == []
