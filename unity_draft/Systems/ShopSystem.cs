using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Minimal shop scaffold: holds inventory, computes price with simple scaling, applies effects to meta/player.
    /// </summary>
    public class ShopSystem : MonoBehaviour
    {
        public GameBalanceConfig balance;
        public MetaProgression meta;
        public Player player;
        public List<ShopItem> inventory = new();

        [Header("Pricing")]
        public float priceExp = 1.12f; // matches SHOP_PRICE_EXP
        public float priceLinear = 0.02f; // SHOP_PRICE_LINEAR
        public float couponDiscountPer = 0.05f; // placeholder
        public int couponMaxUsePerPurchase = 1;
        [Header("Currency Routing")]
        public bool useRunCoinsFirst = false; // allow spending run coins before banked coins
        [Header("Consumable Effects (IDs -> Actions)")]
        public UnityEngine.Events.UnityEvent<string> onConsumableUsed;

        public int GetPrice(ShopItem item, int levelIdx, int ownedCount = 0)
        {
            int couponsUsed = meta != null ? Mathf.Min(meta.coupons, couponMaxUsePerPurchase) : 0;
            float discountMult = 1f - couponDiscountPer * Mathf.Max(0, couponsUsed);
            float exp = Mathf.Pow(priceExp, levelIdx);
            float lin = 1f + priceLinear * levelIdx;
            float stack = Mathf.Pow(1.0f, ownedCount); // placeholder stack factor
            return Mathf.Max(1, Mathf.RoundToInt(item.baseCost * exp * lin * stack * discountMult));
        }

        public bool TryPurchase(ShopItem item, int levelIdx)
        {
            if (meta == null || item == null) return false;
            int price = GetPrice(item, levelIdx);
            int totalCoins = meta.bankedCoins + (useRunCoinsFirst ? meta.runCoins : 0);
            if (totalCoins < price) return false;
            int remaining = price;
            if (useRunCoinsFirst && meta.runCoins > 0)
            {
                int useRun = Mathf.Min(meta.runCoins, remaining);
                meta.SpendRunCoins(useRun);
                remaining -= useRun;
            }
            if (remaining > 0) meta.SpendBankedCoins(remaining);
            meta.ConsumeCoupons(couponMaxUsePerPurchase);
            ApplyItem(item);
            return true;
        }

        private void ApplyItem(ShopItem item)
        {
            // Apply to player/meta; extend with upgrade flags
            if (player != null)
            {
                player.attack += item.addAttack;
                player.speed += item.addSpeed;
                if (item.addRangeMult != 0f)
                {
                    player.rangeMult += item.addRangeMult;
                }
                player.shieldHp = Mathf.Max(player.shieldHp, item.addShield);
            }
            if (meta != null)
            {
                meta.AddCoupon(item.addCoupons);
                meta.AddRunCoins(item.addRunCoins);
                meta.AddBankedCoins(item.addBankedCoins);
                meta.AddKill(item.addKills);
                if (!string.IsNullOrEmpty(item.consumableId) && item.consumableCount > 0)
                {
                    meta.AddConsumable(item.consumableId, item.consumableCount);
                }
                if (item.activateWanted)
                {
                    meta.ActivateWanted(item.wantedBounty > 0 ? item.wantedBounty : meta.killCount + 5);
                }
                if (!string.IsNullOrEmpty(item.consumableEffect))
                {
                    // fire-and-forget effect ID for external listeners (e.g., heal, buff, reroll)
                    onConsumableUsed?.Invoke(item.consumableEffect);
                }
            }
        }
    }
}
