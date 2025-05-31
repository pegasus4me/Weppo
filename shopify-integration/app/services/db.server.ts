import prisma from "../utils/prisma";


/**
 * Create or update a conversation in the database
 * @param {string} conversationId - The conversation ID
 * @returns {Promise<Object>} - The created or updated conversation
 */
export async function createOrUpdateConversation(conversationId: string) {
  try {
    const existingConversation = await prisma.conversation.findUnique({
      where: {
          id: conversationId
      }
    });

    if (existingConversation) {
      return await prisma.conversation.update({
        where: { id: conversationId },
        data: {
          updatedAt: new Date()
        }
      });
    }

    return await prisma.conversation.create({
      data: {
        id: conversationId
      }
    });
  } catch (error) {
    console.error('Error creating/updating conversation:', error);
    throw error;
  }
}

/**
* Save a message to the database - takes the conversationId as parent 
* @param {string} conversationId - The conversation ID
* @param {string} role - The message role (user or assistant)
* @param {string} content - The message content
* @returns {Promise<Object>} - The saved message
*/
export async function saveMessage(conversationId: string, role: string, content: string) {
  try {
    // Ensure the conversation exists
    await createOrUpdateConversation(conversationId);

    // Create the message
    return await prisma.message.create({
      data: {
        conversationId,
        role,
        content
      }
    });
  } catch (error) {
    console.error('Error saving message:', error);
    throw error;
  }
}

/**
* Get conversation history
* @param {string} conversationId - The conversation ID
* @returns {Promise<Array>} - Array of messages in the conversation
*/
export async function getConversationHistory(conversationId: string) {
  try {
    const messages = await prisma.message.findMany({
      where: { conversationId },
      orderBy: { createdAt: 'asc' }
    });
    
    return messages;
  } catch (error) {
    console.error('Error retrieving conversation history:', error);
    return [];
  }
}

// ------------------------------------------------------------------------------------------------------------------------
// -------------------------------------- Customer account MPC server functionalites --------------------------------------
// ------------------------------------------------------------------------------------------------------------------------

// /**
//  * Store a code verifier for PKCE authentication
//  * @param {string} state - The state parameter used in OAuth flow
//  * @param {string} verifier - The code verifier to store
//  * @returns {Promise<Object>} - The saved code verifier object
//  */
// export async function storeCodeVerifier(state: string, verifier: string) : Promise<{
//     id: string;
//     state: string;
//     verifier: string;
//     createdAt: Date;
//     expiresAt: Date;
// }> {
//     // Calculate expiration date (30 minutes from now)
//     const expiresAt = new Date();
//     expiresAt.setMinutes(expiresAt.getMinutes() + 30);
  
//     try {
//       return await prisma.codeVerifier.create({
//         data: {
//          id: `cv_${Date.now()}`,
//           state,
//           verifier,
//           expiresAt
//         }
//       });
//     } catch (error) {
//       console.error('Error storing code verifier:', error);
//       throw error;
//     }
// }


// /**
//  * Get a code verifier by state parameter
//  * @param {string} state - The state parameter used in OAuth flow
//  * @returns {Promise<Object|null>} - The code verifier object or null if not found
//  */
// export async function getCodeVerifier(state: string) : Promise<{
//     id: string;
//     state: string;
//     verifier: string;
//     createdAt: Date;
//     expiresAt: Date;
// } | null> {
//     try {

//       const verifier = await prisma.codeVerifier.findFirst({
//         where: {
//           state,
//           expiresAt: {
//             gt: new Date()
//           }
//         }
//       });
  
//       if (verifier) {
//         // Delete it after retrieval to prevent reuse
//         await prisma.codeVerifier.delete({
//           where: {
//             id: verifier.id
//           }
//         });
//       }
  
//       return verifier;
//     } catch (error) {
//       console.error('Error retrieving code verifier:', error);
//       return null;
//     }
// }

// // @model CustomerToken 
// /**
//  * Store a customer access token in the database
//  * @param {string} conversationId - The conversation ID to associate with the token
//  * @param {string} accessToken - The access token to store
//  * @param {string} refreshToken - The refresh token (optional)
//  * @param {Date} expiresAt - When the token expires
//  * @returns {Promise<Object>} - The saved customer token
//  */
// export async function storeCustomerToken(
//     conversationId: string, 
//     accessToken: string, 
//     refreshToken: string, 
//     expiresAt: Date
// ) {

//     try {
//         // Check if a token already exists for this conversation
//      const existingToken = await prisma.customerToken.findFirst({
//         where: { conversationId }
//       });
  
//     // If a token already exists, update it
//       if (existingToken) {
//         // Update existing token
//         return await prisma.customerToken.update({
//           where: { id: existingToken.id },
//           data: {
//             accessToken,
//             refreshToken,
//             expiresAt,
//             updatedAt: new Date()
//           }
//         });
//       }

//     // Create a new token record if the token does not exist
//     return await prisma.customerToken.create({
//         data: {
//           id: `ct_${Date.now()}`,
//           conversationId,
//           accessToken,
//           refreshToken,
//           expiresAt,
//           createdAt: new Date(),
//           updatedAt: new Date()
//         }
//       });
//     } catch (error: any ) {
//         console.error('Error storing customer token:', error);
//         throw error;
//     }
// }

// /**
//  * Get a customer access token by conversation ID
//  * @param {string} conversationId - The conversation ID
//  * @returns {Promise<Object|null>} - The customer token or null if not found/expired
//  */
// export async function getCustomerToken(conversationId: string) {
//     try {
//       const token = await prisma.customerToken.findFirst({
//         where: {
//           conversationId,
//           expiresAt: {
//             gt: new Date() // Only return non-expired tokens
//           }
//         }
//       });
      
//       return token;
//     } catch (error) {
//       console.error('Error retrieving customer token:', error);
//       return null;
//     }
//   }
  


// /**
//  * Store customer account URL for a conversation
//  * @param {string} conversationId - The conversation ID
//  * @param {string} url - The customer account URL
//  * @returns {Promise<Object>} - The saved URL object
//  */
// export async function storeCustomerAccountUrl(conversationId: string, url: string) {
//   try {
//     return await prisma.customerAccountUrl.upsert({
//       where: { conversationId },
//       update: { 
//         url,
//         updatedAt: new Date()
//       },
//       create: {
//         conversationId,
//         url,
//         updatedAt: new Date()
//       }
//     });
//   } catch (error) {
//     console.error('Error storing customer account URL:', error);
//     throw error;
//   }
// }

// /**
//  * Get customer account URL for a conversation
//  * @param {string} conversationId - The conversation ID
//  * @returns {Promise<string|null>} - The customer account URL or null if not found
//  */
// export async function getCustomerAccountUrl(conversationId: string) {
//   try {
//     const record = await prisma.customerAccountUrl.findUnique({
//       where: { conversationId }
//     });
    
//     return record?.url || null;
//   } catch (error) {
//     console.error('Error retrieving customer account URL:', error);
//     return null;
//   }
// }

