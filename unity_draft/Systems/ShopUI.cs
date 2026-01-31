using UnityEngine;
using UnityEngine.UI;
using TMPro;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple shop UI stub. Hook up buttons to purchase items.
    /// </summary>
    public class ShopUI : MonoBehaviour
    {
        public ShopSystem shop;
        public Transform contentRoot;
        public GameObject itemEntryPrefab;
        public int levelIdx;
        [Header("Bindings")]
        public TextMeshProUGUI coinsText;
        public TextMeshProUGUI couponsText;
        public TextMeshProUGUI couponLevelText;
        public TextMeshProUGUI rerollCostText;
        public Button rerollButton;
        public Transform ownedListRoot;
        public GameObject ownedEntryPrefab;

        private void Start()
        {
            Populate();
        }

        public void Populate()
        {
            if (shop == null || contentRoot == null || itemEntryPrefab == null) return;
            BindMeta();
            foreach (Transform child in contentRoot) Destroy(child.gameObject);
            foreach (var item in shop.inventory)
            {
                var go = Instantiate(itemEntryPrefab, contentRoot);
                var ui = go.GetComponent<ShopUIEntry>();
                if (ui != null) ui.Bind(item, shop, levelIdx);
            }
            PopulateOwned();
            BindReroll();
        }

        public void BindMeta()
        {
            if (shop == null || shop.meta == null) return;
            if (coinsText) coinsText.text = (shop.meta.runCoins + shop.meta.bankedCoins).ToString();
            if (couponsText) couponsText.text = shop.meta.coupons.ToString();
            if (couponLevelText) couponLevelText.text = $"Lv {shop.meta.couponLevel}";
        }

        private void BindReroll()
        {
            if (rerollCostText != null && shop != null)
            {
                rerollCostText.text = $"Reroll: {shop.CurrentRerollCost(levelIdx)}";
            }
            if (rerollButton != null)
            {
                rerollButton.onClick.RemoveAllListeners();
                rerollButton.onClick.AddListener(() => {
                    shop.TryReroll(levelIdx);
                    Populate();
                });
            }
        }

        private void PopulateOwned()
        {
            if (ownedListRoot == null || ownedEntryPrefab == null || shop == null) return;
            foreach (Transform child in ownedListRoot) Destroy(child.gameObject);
            foreach (var id in shop.ownedItems)
            {
                var go = Instantiate(ownedEntryPrefab, ownedListRoot);
                var text = go.GetComponentInChildren<TextMeshProUGUI>();
                if (text != null) text.text = id;
            }
        }
    }

    public class ShopUIEntry : MonoBehaviour
    {
        public TextMeshProUGUI nameText;
        public TextMeshProUGUI descText;
        public TextMeshProUGUI priceText;
        public TextMeshProUGUI ownedText;
        public Button buyButton;

        private ShopItem _item;
        private ShopSystem _shop;
        private int _levelIdx;

        public void Bind(ShopItem item, ShopSystem shop, int levelIdx)
        {
            _item = item;
            _shop = shop;
            _levelIdx = levelIdx;
            if (nameText) nameText.text = item.displayName;
            if (descText) descText.text = item.description;
            RefreshPrice();
            RefreshOwned();
            if (buyButton)
            {
                buyButton.onClick.RemoveAllListeners();
                buyButton.onClick.AddListener(Buy);
            }
        }

        private void RefreshPrice()
        {
            if (priceText && _shop != null && _item != null)
            {
                int price = _shop.GetPrice(_item, _levelIdx);
                priceText.text = price.ToString();
            }
        }

        private void RefreshOwned()
        {
            if (ownedText && _shop != null && _item != null)
            {
                bool owned = _shop.ownedItems.Contains(_item.itemId);
                ownedText.text = owned ? "Owned" : string.Empty;
            }
        }

        private void Buy()
        {
            if (_shop != null && _item != null)
            {
                _shop.TryPurchase(_item, _levelIdx);
                RefreshPrice();
                RefreshOwned();
            }
        }
    }
}
