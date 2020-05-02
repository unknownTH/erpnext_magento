## ERPNext Magento

Magento connector for ERPNext



### License

GNU GPL v3.0



### Limitations

#### Customers
- New ERPNext customers are not synced to Magento.
- New ERPNext customer adresses are not synced to Magento.

#### Products
- Images are not synced.
- Stock qty is not synced.
- Dosen't work with product options (use conifgurable product instead).
- Beside the price only the default item values are synced from Magento to ERPNext.
- Item Variants can only be dectivated for all Websites.
- Virtual Products are always set to visiblity 1 (Not Visible Individually), when synced from ERPNext to Magento.

#### Orders
- Tax has to be included in price rate.
- Shipping Costs are not synced from Magento to ERPNext
- When a Magento order is snced to ERPNext it will automatically marked as completed in Magento. Delivery and payment tracking has to be done in ERPNext.
