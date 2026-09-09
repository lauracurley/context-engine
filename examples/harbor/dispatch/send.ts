export function dispatchParcel(parcelCode: string) {
  return { topic: "parcel.dispatched", parcelCode, state: "IN_TRANSIT" };
}
