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
        public List<string> ownedItems = new();

        [Header("Pricing")]
        public float priceExp = 1.12f; // matches SHOP_PRICE_EXP
        public float priceLinear = 0.02f; // SHOP_PRICE_LINEAR
        public float couponDiscountPer = 0.05f; // placeholder
        public int couponMaxUsePerPurchase = 1;
        [Header("Currency Routing")]
        public bool useRunCoinsFirst = false; // allow spending run coins before banked coins
        [Header("Consumable Effects (IDs -> Actions)")]
        public UnityEngine.Events.UnityEvent<string> onConsumableUsed;
        [Header("UI Bindings (optional)")]
        public UI.MenuController menu;

        public int GetPrice(ShopItem item, int levelIdx, int ownedCount = 0)
        {
            int couponsUsed = meta != null ? Mathf.Min(meta.coupons + meta.couponLevel, couponMaxUsePerPurchase) : 0;
            float discountMult = 1f - couponDiscountPer * Mathf.Max(0, couponsUsed);
            float exp = Mathf.Pow(priceExp, levelIdx);
            float lin = 1f + priceLinear * levelIdx;
            float stack = Mathf.Pow(1.15f, ownedCount); // mild stack like Python SHOP_PRICE_STACK
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
            if (!ownedItems.Contains(item.itemId)) ownedItems.Add(item.itemId);
            menu?.BindMeta(meta, null);
            return true;
        }

        private void ApplyItem(ShopItem item)
        {
            // Apply to player/meta; extend with upgrade flags
            if (player != null)
            {
                switch (item.upgradeEffect)
                {
                    case UpgradeEffect.Attack:
                        player.attack += Mathf.RoundToInt(item.addAttack != 0 ? item.addAttack : item.baseCost * 0.05f);
                        break;
                    case UpgradeEffect.Speed:
                        player.speed += item.addSpeed != 0 ? item.addSpeed : 0.2f;
                        break;
                    case UpgradeEffect.RangeMult:
                        player.rangeMult += item.addRangeMult != 0f ? item.addRangeMult : 0.05f;
                        break;
                    case UpgradeEffect.Shield:
                        player.shieldHp = Mathf.Max(player.shieldHp, item.addShield > 0 ? item.addShield : 10);
                        break;
                    case UpgradeEffect.CritChance:
                        player.critChance += 0.02f;
                        break;
                    case UpgradeEffect.CritMult:
                        player.critMult += 0.1f;
                        break;
                    case UpgradeEffect.BonePlating:
                        Systems.StatusEffect.ApplyBonePlating(player.gameObject, 20);
                        break;
                    case UpgradeEffect.Carapace:
                        Systems.StatusEffect.ApplyCarapace(player.gameObject, 30);
                        break;
                    default:
                        break;
                }
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
                meta.couponLevel += (item.upgradeEffect == UpgradeEffect.Coupon) ? 1 : 0;
                meta.AddRunCoins(item.addRunCoins);
                meta.AddBankedCoins(item.addBankedCoins);
                meta.AddKill(item.addKills);
                if (item.upgradeEffect == UpgradeEffect.Coupon) meta.AddCoupon(Mathf.Max(1, item.addCoupons));
                if (item.upgradeEffect == UpgradeEffect.WantedBounty) meta.ActivateWanted(Mathf.RoundToInt(item.wantedBounty > 0 ? item.wantedBounty : 5));
                if (item.upgradeEffect == UpgradeEffect.RunCoins) meta.AddRunCoins(Mathf.RoundToInt(Mathf.Max(item.addRunCoins, item.baseCost * 0.2f)));
                if (item.upgradeEffect == UpgradeEffect.BankCoins) meta.AddBankedCoins(Mathf.RoundToInt(Mathf.Max(item.addBankedCoins, item.baseCost * 0.1f)));
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
                    ApplyConsumableEffect(item.consumableEffect);
                }
            }
        }

        private void ApplyConsumableEffect(string effectId)
        {
            if (player == null || meta == null || string.IsNullOrEmpty(effectId)) return;
            switch (effectId)
            {
                case "heal_big":
                    player.hp = Mathf.Min(player.maxHp, player.hp + 25);
                    break;
                case "reroll_shop":
                    // simple reroll: shuffle inventory order
                    inventory.Sort((a, b) => Random.Range(-1, 2));
                    break;
                case "clear_wanted":
                    meta.ClearWanted();
                    break;
                case "gold_bonus":
                    meta.AddRunCoins(30);
                    break;
                case "coupon_gain":
                    meta.AddCoupon(2);
                    break;
            }
        }
    }
}
