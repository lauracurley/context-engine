# Delivery operations

The dispatch service emits parcel.dispatched with parcelCode and IN_TRANSIT.
The delivery receipt changes the parcel state to DELIVERED.
If a parcel remains IN_TRANSIT, inspect the delivery receipt consumer.
This fixture describes that consumer; its implementation is not included.
