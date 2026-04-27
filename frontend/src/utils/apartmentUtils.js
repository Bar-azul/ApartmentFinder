export function formatPrice(price) {
  if (price === null || price === undefined || price === "") return "מחיר לא צוין";

  const numericPrice = Number(price);

  if (Number.isNaN(numericPrice)) return "מחיר לא צוין";

  return `₪ ${numericPrice.toLocaleString("he-IL")}`;
}

export function getYad2Url(apartment) {
  if (apartment?.yad2_url) return apartment.yad2_url;

  if (apartment?.token) {
    return `https://www.yad2.co.il/realestate/item/center-and-sharon/${apartment.token}`;
  }

  return "https://www.yad2.co.il/realestate/rent";
}