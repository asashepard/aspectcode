// Should trigger: arch.data_model
using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace MyApp.Models
{
    // Entity Framework data model
    [Table("Users")]
    public class User
    {
        [Key]
        public int Id { get; set; }

        [Required]
        [MaxLength(100)]
        public string Username { get; set; }

        [Required]
        [EmailAddress]
        public string Email { get; set; }

        public bool IsActive { get; set; } = true;
        
        public DateTime CreatedAt { get; set; }
    }

    // Record data model (C# 9+)
    public record Order(string OrderId, int UserId, decimal Amount);
}
