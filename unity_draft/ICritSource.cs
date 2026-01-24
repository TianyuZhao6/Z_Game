namespace ZGame.UnityDraft
{
    /// <summary>
    /// Simple crit source interface for bullets to query crit stats from players/enemies.
    /// </summary>
    public interface ICritSource
    {
        float CritChance { get; }
        float CritMult { get; }
    }
}
