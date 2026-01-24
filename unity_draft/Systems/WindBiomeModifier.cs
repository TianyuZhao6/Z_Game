using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Applies a directional wind force to enemies and player in a given biome.
    /// Enable/disable when biome is wind.
    /// </summary>
    public class WindBiomeModifier : MonoBehaviour
    {
        public string biomeName = "Domain of Wind";
        public Vector2 windDir = new Vector2(1, 0);
        public float windForce = 0.8f;

        public void ApplyIfBiome(string biome, Rigidbody2D rb)
        {
            if (rb == null) return;
            if (string.IsNullOrEmpty(biome) || biome != biomeName) return;
            rb.AddForce(windDir.normalized * windForce, ForceMode2D.Force);
        }
    }
}
